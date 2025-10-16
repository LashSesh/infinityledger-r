//! In-memory backend implementation

use std::collections::HashMap;
use mef_schemas::MemoryItem;
use crate::backend::{MemoryBackend, SearchResult};

/// Simple in-memory backend using HashMap
pub struct InMemoryBackend {
    items: HashMap<String, MemoryItem>,
}

impl InMemoryBackend {
    /// Create a new in-memory backend
    pub fn new() -> Self {
        Self {
            items: HashMap::new(),
        }
    }
}

impl Default for InMemoryBackend {
    fn default() -> Self {
        Self::new()
    }
}

impl MemoryBackend for InMemoryBackend {
    fn store(&mut self, item: MemoryItem) -> crate::Result<()> {
        self.items.insert(item.id.clone(), item);
        Ok(())
    }
    
    fn get(&self, id: &str) -> crate::Result<Option<MemoryItem>> {
        Ok(self.items.get(id).cloned())
    }
    
    fn search(&self, query: &[f64], k: usize) -> crate::Result<Vec<SearchResult>> {
        if query.len() != 8 {
            return Err(crate::MemoryError::InvalidQuery(
                format!("Expected 8D query vector, got {}", query.len())
            ));
        }
        
        // Compute L2 distances
        let mut results: Vec<SearchResult> = self.items
            .values()
            .map(|item| {
                let distance = l2_distance(query, &item.vector);
                SearchResult {
                    item: item.clone(),
                    distance,
                }
            })
            .collect();
        
        // Sort by distance (ascending)
        results.sort_by(|a, b| a.distance.partial_cmp(&b.distance).unwrap());
        
        // Take top k
        results.truncate(k);
        
        Ok(results)
    }
    
    fn remove(&mut self, id: &str) -> crate::Result<()> {
        self.items.remove(id);
        Ok(())
    }
    
    fn clear(&mut self) -> crate::Result<()> {
        self.items.clear();
        Ok(())
    }
    
    fn count(&self) -> usize {
        self.items.len()
    }
}

/// Compute L2 distance between two vectors
fn l2_distance(a: &[f64], b: &[f64]) -> f64 {
    a.iter()
        .zip(b.iter())
        .map(|(x, y)| (x - y).powi(2))
        .sum::<f64>()
        .sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;
    use mef_schemas::SpectralSignature;

    #[test]
    fn test_in_memory_backend() {
        let mut backend = InMemoryBackend::new();
        
        let val = 1.0 / (8.0_f64).sqrt();
        let vector = vec![val; 8];
        let spectral = SpectralSignature {
            psi: 0.3,
            rho: 0.3,
            omega: 0.4,
        };
        
        let item = MemoryItem::new(
            "mem_001".to_string(),
            vector,
            spectral,
            None,
        ).unwrap();
        
        backend.store(item).unwrap();
        assert_eq!(backend.count(), 1);
        
        let retrieved = backend.get("mem_001").unwrap();
        assert!(retrieved.is_some());
    }

    #[test]
    fn test_search() {
        let mut backend = InMemoryBackend::new();
        
        // Store two items
        let val1 = 1.0 / (8.0_f64).sqrt();
        let vector1 = vec![val1; 8];
        let spectral = SpectralSignature {
            psi: 0.3,
            rho: 0.3,
            omega: 0.4,
        };
        
        let item1 = MemoryItem::new(
            "mem_001".to_string(),
            vector1.clone(),
            spectral,
            None,
        ).unwrap();
        
        backend.store(item1).unwrap();
        
        // Search
        let results = backend.search(&vector1, 1).unwrap();
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].item.id, "mem_001");
    }

    #[test]
    fn test_l2_distance() {
        let a = vec![0.0, 0.0, 0.0];
        let b = vec![1.0, 0.0, 0.0];
        let dist = l2_distance(&a, &b);
        assert!((dist - 1.0).abs() < 1e-6);
    }
}
