/*!
 * MEF-Core Benchmark Drivers
 * 
 * This crate provides driver implementations for benchmarking vector stores.
 * Migrated from MEF-Core_v1.0/src/bench/drivers/
 */

pub mod base;
pub mod mef_driver;
pub mod faiss_baseline;

// Re-export commonly used types
pub use base::{DriverUnavailable, UpsertItem, Vector, VectorStoreDriver};
pub use mef_driver::MEFDriver;
pub use faiss_baseline::FaissBaselineDriver;

use std::collections::HashMap;

/// Driver registry mapping names to driver constructors
pub fn get_driver_registry() -> HashMap<String, fn(Option<&str>) -> Box<dyn VectorStoreDriver>> {
    let mut registry: HashMap<String, fn(Option<&str>) -> Box<dyn VectorStoreDriver>> = HashMap::new();
    
    registry.insert(
        "mef".to_string(),
        |metric| Box::new(MEFDriver::new(metric)) as Box<dyn VectorStoreDriver>,
    );
    
    registry.insert(
        "faiss".to_string(),
        |metric| Box::new(FaissBaselineDriver::new(metric)) as Box<dyn VectorStoreDriver>,
    );
    
    registry
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_driver_registry() {
        let registry = get_driver_registry();
        assert!(registry.contains_key("mef"));
        assert!(registry.contains_key("faiss"));
    }

    #[test]
    fn test_create_mef_driver_from_registry() {
        let registry = get_driver_registry();
        let constructor = registry.get("mef").unwrap();
        let driver = constructor(Some("cosine"));
        assert_eq!(driver.name(), "MEF");
        assert_eq!(driver.metric(), "cosine");
    }

    #[test]
    fn test_create_faiss_driver_from_registry() {
        let registry = get_driver_registry();
        let constructor = registry.get("faiss").unwrap();
        let driver = constructor(Some("l2"));
        assert_eq!(driver.name(), "faiss-baseline");
        assert_eq!(driver.metric(), "l2");
    }
}
