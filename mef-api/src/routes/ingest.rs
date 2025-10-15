/// Ingestion endpoints
use axum::{
    extract::State,
    routing::post,
    Json, Router,
};
use chrono::Utc;

use crate::{error::ApiError, models::*, AppState, Result};
use mef_ingestion::normalize_payload;
use mef_spiral::SpiralSnapshot;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/ingest", post(ingest))
        .route("/acquisition", post(acquisition))
}

/// Ingest data into MEF-Core system
async fn ingest(
    State(state): State<AppState>,
    Json(request): Json<IngestRequest>,
) -> Result<Json<IngestResponse>> {
    // Normalize the payload based on data type
    let normalized = normalize_payload(&request.data, &request.data_type)
        .map_err(|e| ApiError::InvalidInput(format!("Failed to normalize payload: {}", e)))?;
    
    // Create spiral snapshot handler
    let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref())
        .map_err(|e| ApiError::Internal(format!("Failed to create spiral snapshot: {}", e)))?;
    
    // Create snapshot
    let snapshot = spiral.create_snapshot(
        normalized,
        &request.seed,
        &request.data_type,
    ).map_err(|e| ApiError::Processing(format!("Failed to create snapshot: {}", e)))?;
    
    // Save the snapshot
    let snapshot_path = spiral.save_snapshot(&snapshot)
        .map_err(|e| ApiError::Storage(format!("Failed to save snapshot: {}", e)))?;
    
    // Get snapshot ID from the path
    let snapshot_id = snapshot_path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();
    
    // Get metrics
    let phase = snapshot.phase;
    let por_result = snapshot.por.clone();
    
    Ok(Json(IngestResponse {
        snapshot_id: snapshot_id.clone(),
        phase,
        por: por_result,
        hash: snapshot.hash.clone(),
        timestamp: Utc::now().to_rfc3339(),
    }))
}

/// Acquisition endpoint - alternative ingestion method
async fn acquisition(
    State(state): State<AppState>,
    Json(request): Json<AcquisitionRequest>,
) -> Result<Json<AcquisitionResponse>> {
    // Convert JSON value to normalized vector
    let data_str = serde_json::to_string(&request.data)
        .map_err(|e| ApiError::InvalidInput(e.to_string()))?;
    
    // Use default seed from config
    let seed = &state.config.seed;
    
    // Normalize as JSON type
    let normalized = normalize_payload(&data_str, "json")
        .map_err(|e| ApiError::InvalidInput(format!("Failed to normalize payload: {}", e)))?;
    
    // Create spiral snapshot handler
    let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref())
        .map_err(|e| ApiError::Internal(format!("Failed to create spiral snapshot: {}", e)))?;
    
    // Create snapshot
    let snapshot = spiral.create_snapshot(
        normalized,
        seed,
        "json",
    ).map_err(|e| ApiError::Processing(format!("Failed to create snapshot: {}", e)))?;
    
    // Save snapshot
    let snapshot_path = spiral.save_snapshot(&snapshot)
        .map_err(|e| ApiError::Storage(format!("Failed to save snapshot: {}", e)))?;
    
    let snapshot_id = snapshot_path.file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("unknown")
        .to_string();
    
    Ok(Json(AcquisitionResponse {
        success: true,
        vector_id: snapshot_id,
        collection: state.config.quality_collection.clone(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ApiConfig;
    
    #[tokio::test]
    async fn test_ingest_basic() {
        let config = ApiConfig::default();
        let state = AppState::new(config).await.unwrap();
        
        let request = IngestRequest {
            data: "test data".to_string(),
            data_type: "text".to_string(),
            seed: "test_seed".to_string(),
        };
        
        let result = ingest(State(state), Json(request)).await;
        assert!(result.is_ok());
    }
}
