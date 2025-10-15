/// Application state for API server
use anyhow::Result;
use std::sync::{Arc, Mutex};
use std::path::PathBuf;

use crate::config::ApiConfig;
use mef_spiral::SpiralConfig;
use mef_ledger::MEFLedger;

/// Shared application state
#[derive(Clone)]
pub struct AppState {
    pub config: Arc<ApiConfig>,
    pub spiral_config: Arc<SpiralConfig>,
    pub store_path: Arc<PathBuf>,
    pub ledger: Arc<Mutex<MEFLedger>>,
}

impl AppState {
    /// Create new application state with initialized components
    pub async fn new(config: ApiConfig) -> Result<Self> {
        // Initialize spiral configuration
        let spiral_config = SpiralConfig::default();
        let store_path = config.store_path.clone();
        
        // Initialize ledger  
        let ledger = MEFLedger::new(&config.ledger_path)?;
        
        Ok(Self {
            config: Arc::new(config),
            spiral_config: Arc::new(spiral_config),
            store_path: Arc::new(store_path),
            ledger: Arc::new(Mutex::new(ledger)),
        })
    }
}
