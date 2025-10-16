//! # Metatron Adapter
//!
//! Provides integration with the Metatron router from mef-topology without
//! modifying core behavior.
//!
//! ## SPEC-006 Reference
//!
//! From Part 1, Section 1.3:
//! - Use adapters/shims to avoid editing core files
//! - Metatron access via topology/ or metatron_vendor/
//!
//! ## Mode
//!
//! Supports two operational modes:
//! - `inproc`: In-process adapter (reads from mef-topology directly)
//! - `service`: External service call (for distributed deployments)

use mef_schemas::RouteSpec;
use std::collections::HashMap;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AdapterError {
    #[error("Metatron service unavailable: {0}")]
    ServiceUnavailable(String),
    
    #[error("Invalid metrics: {0}")]
    InvalidMetrics(String),
    
    #[error("Mode not supported: {0}")]
    UnsupportedMode(String),
}

/// Metatron router operational mode
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouterMode {
    /// In-process adapter (default)
    InProc,
    
    /// External service call
    Service,
}

impl Default for RouterMode {
    fn default() -> Self {
        Self::InProc
    }
}

/// Metatron adapter for route selection
///
/// This adapter integrates with the existing Metatron router in mef-topology
/// without modifying its implementation. It acts as a bridge between the
/// knowledge engine and the core topology module.
pub struct MetatronAdapter {
    mode: RouterMode,
    service_url: Option<String>,
}

impl Default for MetatronAdapter {
    fn default() -> Self {
        Self::new(RouterMode::InProc, None)
    }
}

impl MetatronAdapter {
    /// Create a new adapter
    ///
    /// ## Arguments
    ///
    /// * `mode` - Operational mode (inproc or service)
    /// * `service_url` - URL for service mode (required if mode is Service)
    pub fn new(mode: RouterMode, service_url: Option<String>) -> Self {
        Self { mode, service_url }
    }
    
    /// Get route from Metatron based on seed and mesh metrics
    ///
    /// ## In-Process Mode
    ///
    /// Calls into mef-topology to:
    /// 1. Get current mesh metrics (Betti, lambda_gap, persistence)
    /// 2. Select route using S7 permutation space
    ///
    /// ## Service Mode
    ///
    /// Makes HTTP request to external Metatron service.
    ///
    /// ## TODO
    ///
    /// - Implement actual call to mef-topology for mesh metrics
    /// - Implement service mode HTTP client
    /// - Add retry logic for service unavailability
    /// - Add caching for frequently used routes
    pub async fn get_route(
        &self,
        seed: &str,
        _context: Option<serde_json::Value>,
    ) -> Result<RouteSpec, AdapterError> {
        match self.mode {
            RouterMode::InProc => {
                // TODO: Get actual mesh metrics from mef-topology
                // For now, use placeholder metrics
                let mesh_metrics = self.get_mesh_metrics_inproc().await?;
                
                // Select route using S7 algorithm
                let route = crate::s7::select_route(seed, &mesh_metrics);
                
                Ok(route)
            }
            RouterMode::Service => {
                if self.service_url.is_none() {
                    return Err(AdapterError::ServiceUnavailable(
                        "Service URL not configured".to_string()
                    ));
                }
                
                // TODO: Implement HTTP client for service mode
                Err(AdapterError::UnsupportedMode(
                    "Service mode not yet implemented".to_string()
                ))
            }
        }
    }
    
    /// Get mesh metrics from mef-topology (in-process)
    ///
    /// ## TODO
    ///
    /// This should call into mef-topology to get:
    /// - Betti numbers from topological analysis
    /// - Lambda gap from spectral analysis
    /// - Persistence intervals from homology
    ///
    /// For now, returns placeholder metrics.
    async fn get_mesh_metrics_inproc(&self) -> Result<HashMap<String, f64>, AdapterError> {
        // TODO: Call mef-topology::compute_mesh_metrics()
        // This requires defining the interface with mef-topology
        
        tracing::debug!("Using placeholder mesh metrics (TODO: integrate with mef-topology)");
        
        let mut metrics = HashMap::new();
        metrics.insert("betti".to_string(), 2.0);
        metrics.insert("lambda_gap".to_string(), 0.5);
        metrics.insert("persistence".to_string(), 0.3);
        
        Ok(metrics)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_adapter_inproc() {
        let adapter = MetatronAdapter::default();
        let runtime = tokio::runtime::Runtime::new().unwrap();
        
        let result = runtime.block_on(adapter.get_route("test_seed", None));
        
        assert!(result.is_ok());
        let route = result.unwrap();
        assert_eq!(route.sigma.len(), 7);
        assert_eq!(route.permutation.len(), 7);
    }

    #[test]
    fn test_adapter_service_not_configured() {
        let adapter = MetatronAdapter::new(RouterMode::Service, None);
        let runtime = tokio::runtime::Runtime::new().unwrap();
        
        let result = runtime.block_on(adapter.get_route("test_seed", None));
        
        assert!(result.is_err());
    }

    #[test]
    fn test_adapter_deterministic() {
        let adapter = MetatronAdapter::default();
        let runtime = tokio::runtime::Runtime::new().unwrap();
        
        let route1 = runtime.block_on(adapter.get_route("seed123", None)).unwrap();
        let route2 = runtime.block_on(adapter.get_route("seed123", None)).unwrap();
        
        assert_eq!(route1.route_id, route2.route_id);
        assert_eq!(route1.sigma, route2.sigma);
    }
}
