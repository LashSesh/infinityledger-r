/*!
 * Driver for Qdrant's HTTP API.
 * 
 * Migrated from MEF-Core_v1.0/src/bench/drivers/qdrant_driver.py
 * 
 * This implementation uses the Qdrant HTTP API directly via reqwest
 * instead of the qdrant-client library to minimize dependencies.
 */

use crate::base::{DriverUnavailable, UpsertItem, Vector, VectorStoreDriver};
use anyhow::{Context, Result};
use serde_json::json;

/// Benchmark driver that interacts with a Qdrant deployment via HTTP API
pub struct QdrantDriver {
    metric: String,
    base_url: String,
    client: Option<reqwest::blocking::Client>,
    dimension: Option<usize>,
}

impl QdrantDriver {
    /// Create a new Qdrant driver
    pub fn new(metric: Option<&str>) -> Self {
        let metric = metric.unwrap_or("cosine").to_lowercase();
        let base_url = std::env::var("QDRANT_URL")
            .unwrap_or_default()
            .trim_end_matches('/')
            .to_string();
        
        Self {
            metric,
            base_url,
            client: None,
            dimension: None,
        }
    }

    fn ensure_collection(&mut self, namespace: &str, dimension: usize) -> Result<()> {
        let client = self.client.as_ref()
            .ok_or_else(|| anyhow::anyhow!("connect() must be called before using the driver"))?;

        let distance = match self.metric.as_str() {
            "cosine" => "Cosine",
            "ip" => "Dot",
            "l2" => "Euclid",
            _ => "Cosine",
        };

        let payload = json!({
            "vectors": {
                "size": dimension,
                "distance": distance
            }
        });

        let url = format!("{}/collections/{}", self.base_url, namespace);
        
        // Try to recreate the collection
        let _ = client
            .delete(&url)
            .timeout(std::time::Duration::from_secs(15))
            .send();

        let response = client
            .put(&url)
            .json(&payload)
            .timeout(std::time::Duration::from_secs(15))
            .send()
            .map_err(|e| {
                DriverUnavailable::new(
                    "Qdrant",
                    format!("failed to ensure collection: {}", e),
                )
            })?;

        if !response.status().is_success() {
            return Err(DriverUnavailable::new(
                "Qdrant",
                format!("failed to create collection: HTTP {}", response.status()),
            )
            .into());
        }

        Ok(())
    }

    fn flush_batch(&self, namespace: &str, batch: Vec<serde_json::Value>) -> Result<()> {
        let client = self.client.as_ref()
            .ok_or_else(|| anyhow::anyhow!("connect() must be called before using the driver"))?;

        let payload = json!({
            "points": batch,
            "wait": true
        });

        let url = format!("{}/collections/{}/points", self.base_url, namespace);
        let response = client
            .put(&url)
            .json(&payload)
            .timeout(std::time::Duration::from_secs(30))
            .send()
            .map_err(|e| {
                DriverUnavailable::new(
                    "Qdrant",
                    format!("failed to upsert batch: {}", e),
                )
            })?;

        if !response.status().is_success() {
            return Err(DriverUnavailable::new(
                "Qdrant",
                format!("failed to upsert batch: HTTP {}", response.status()),
            )
            .into());
        }

        Ok(())
    }
}

impl VectorStoreDriver for QdrantDriver {
    fn name(&self) -> &str {
        "Qdrant"
    }

    fn metric(&self) -> &str {
        &self.metric
    }

    fn connect(&mut self) -> Result<()> {
        if self.base_url.is_empty() {
            return Err(DriverUnavailable::new(
                "Qdrant",
                "QDRANT_URL not configured".to_string(),
            )
            .into());
        }

        let client = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(30))
            .build().context("Failed to build HTTP client")?;

        let health_url = format!("{}/health", self.base_url);
        let response = client
            .get(&health_url)
            .timeout(std::time::Duration::from_secs(5))
            .send()
            .map_err(|e| {
                DriverUnavailable::new(
                    "Qdrant",
                    format!("unable to connect to Qdrant: {}", e),
                )
            })?;

        if !response.status().is_success() {
            return Err(DriverUnavailable::new(
                "Qdrant",
                format!("health check failed: HTTP {}", response.status()),
            )
            .into());
        }

        self.client = Some(client);
        Ok(())
    }

    fn clear(&mut self, namespace: &str) -> Result<()> {
        let client = self.client.as_ref()
            .ok_or_else(|| anyhow::anyhow!("connect() must be called before using the driver"))?;

        let url = format!("{}/collections/{}", self.base_url, namespace);
        let response = client
            .delete(&url)
            .timeout(std::time::Duration::from_secs(15))
            .send()
            .map_err(|e| {
                DriverUnavailable::new(
                    "Qdrant",
                    format!("failed to clear collection: {}", e),
                )
            })?;

        let status = response.status().as_u16();
        if status != 200 && status != 404 {
            return Err(DriverUnavailable::new(
                "Qdrant",
                format!("failed to clear collection: HTTP {}", status),
            )
            .into());
        }

        self.dimension = None;
        Ok(())
    }

    fn upsert(
        &mut self,
        items: Vec<UpsertItem>,
        namespace: &str,
        batch_size: usize,
    ) -> Result<()> {
        if self.client.is_none() {
            return Err(anyhow::anyhow!("connect() must be called before using the driver"));
        }

        let mut batch: Vec<serde_json::Value> = Vec::new();

        for (identifier, vector, metadata) in items {
            if self.dimension.is_none() {
                self.dimension = Some(vector.len());
                self.ensure_collection(namespace, vector.len())?;
            }

            let point = json!({
                "id": identifier,
                "vector": vector,
                "payload": metadata.unwrap_or_default()
            });

            batch.push(point);

            if batch.len() >= batch_size {
                self.flush_batch(namespace, batch.clone())?;
                batch.clear();
            }
        }

        if !batch.is_empty() {
            self.flush_batch(namespace, batch)?;
        }

        Ok(())
    }

    fn search(
        &self,
        query: &Vector,
        k: usize,
        namespace: &str,
    ) -> Result<Vec<(String, f64)>> {
        let client = self.client.as_ref()
            .ok_or_else(|| anyhow::anyhow!("connect() must be called before using the driver"))?;

        let search_body = json!({
            "vector": query,
            "limit": k,
            "with_payload": false,
            "with_vector": false
        });

        let url = format!("{}/collections/{}/points/search", self.base_url, namespace);
        let response = client
            .post(&url)
            .json(&search_body)
            .timeout(std::time::Duration::from_secs(15))
            .send()
            .map_err(|e| {
                DriverUnavailable::new(
                    "Qdrant",
                    format!("search failed: {}", e),
                )
            })?;

        if !response.status().is_success() {
            return Err(DriverUnavailable::new(
                "Qdrant",
                format!("search failed: HTTP {}", response.status()),
            )
            .into());
        }

        let payload: serde_json::Value = response.json().context("Failed to parse search response")?;

        let results = payload
            .get("result")
            .and_then(|r| r.as_array())
            .ok_or_else(|| anyhow::anyhow!("Invalid search response format"))?;

        let mut hits: Vec<(String, f64)> = Vec::new();
        for entry in results {
            if let (Some(id), Some(score)) = (
                entry.get("id").and_then(|v| v.as_str().or_else(|| v.as_u64().map(|n| Box::leak(n.to_string().into_boxed_str()) as &str))),
                entry.get("score").and_then(|v| v.as_f64()),
            ) {
                hits.push((id.to_string(), score));
            }
        }

        Ok(hits.into_iter().take(k).collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_qdrant_driver_creation() {
        let driver = QdrantDriver::new(None);
        assert_eq!(driver.name(), "Qdrant");
        assert_eq!(driver.metric(), "cosine");
    }

    #[test]
    fn test_qdrant_driver_custom_metric() {
        let driver = QdrantDriver::new(Some("l2"));
        assert_eq!(driver.metric(), "l2");
    }

    #[test]
    fn test_qdrant_driver_ip_metric() {
        let driver = QdrantDriver::new(Some("ip"));
        assert_eq!(driver.metric(), "ip");
    }

    #[test]
    fn test_qdrant_driver_base_url_env() {
        std::env::set_var("QDRANT_URL", "http://localhost:6333/");
        let driver = QdrantDriver::new(None);
        assert_eq!(driver.base_url, "http://localhost:6333");
        std::env::remove_var("QDRANT_URL");
    }

    #[test]
    fn test_qdrant_driver_default_url() {
        std::env::remove_var("QDRANT_URL");
        let driver = QdrantDriver::new(None);
        assert_eq!(driver.base_url, "");
    }

    #[test]
    fn test_connect_without_url() {
        let mut driver = QdrantDriver::new(None);
        let result = driver.connect();
        assert!(result.is_err());
        assert!(result.unwrap_err().to_string().contains("QDRANT_URL not configured"));
    }

    #[test]
    fn test_upsert_without_connect() {
        let mut driver = QdrantDriver::new(Some("cosine"));
        let items = vec![
            ("id1".to_string(), vec![1.0, 2.0, 3.0], None),
        ];
        let result = driver.upsert(items, "test", 1000);
        assert!(result.is_err());
    }

    #[test]
    fn test_search_without_connect() {
        let driver = QdrantDriver::new(Some("cosine"));
        let query = vec![1.0, 2.0, 3.0];
        let result = driver.search(&query, 10, "test");
        assert!(result.is_err());
    }

    #[test]
    fn test_clear_without_connect() {
        let mut driver = QdrantDriver::new(Some("cosine"));
        let result = driver.clear("test");
        assert!(result.is_err());
    }
}
