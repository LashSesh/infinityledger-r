/// Processing endpoints - Solve-Coagula and TIC creation
use axum::{
    extract::{Path, State},
    routing::post,
    Json, Router,
};
use chrono::Utc;

use crate::{error::ApiError, models::*, AppState, Result};
use mef_solvecoagula::SolveCoagula;
use mef_tic::TICCrystallizer;
use mef_spiral::SpiralSnapshot;

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/process", post(process))
        .route("/solve", post(solve))
        .route("/validate/snapshot/:id", post(validate))
}

/// Process a snapshot through Solve-Coagula to create a TIC
async fn process(
    State(state): State<AppState>,
    Json(request): Json<ProcessRequest>,
) -> Result<Json<ProcessResponse>> {
    // Create spiral snapshot handler to load
    let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref())
        .map_err(|e| ApiError::Internal(format!("Failed to create spiral snapshot: {}", e)))?;
    
    // Load snapshot
    let snapshot = spiral.load_snapshot(&request.snapshot_id)
        .map_err(|e| ApiError::NotFound(format!("Failed to load snapshot: {}", e)))?
        .ok_or_else(|| ApiError::NotFound(format!("Snapshot {} not found", request.snapshot_id)))?;
    
    // Create Solve-Coagula operator
    let mut solver = SolveCoagula::new(0.8, 1e-6, 1000);
    
    // Process the snapshot - convert coords to the expected format
    let coords_vec = snapshot.coords.iter().flat_map(|c| vec![c.x, c.y, c.z, c.w, c.u]).collect::<Vec<f64>>();
    let result = solver.apply(coords_vec)
        .map_err(|e| ApiError::Processing(format!("Solve-Coagula failed: {}", e)))?;
    
    // Create TIC from result
    let crystallizer = TICCrystallizer::new();
    let tic = crystallizer.crystallize(&result)
        .map_err(|e| ApiError::Processing(format!("TIC crystallization failed: {}", e)))?;
    
    let tic_id = tic.id.clone();
    
    // If commit is requested, append to ledger
    if request.commit.unwrap_or(false) {
        // TODO: Implement ledger append with proper TIC/snapshot data
        tracing::info!("Commit requested for TIC: {}", tic_id);
    }
    
    Ok(Json(ProcessResponse {
        tic_id,
        converged: result.converged,
        iterations: result.iterations,
        final_eigenvalue: result.final_eigenvalue,
        timestamp: Utc::now().to_rfc3339(),
    }))
}

/// Solve endpoint - alternative processing method
async fn solve(
    State(state): State<AppState>,
    Json(request): Json<SolveRequest>,
) -> Result<Json<SolveResponse>> {
    // Create spiral snapshot handler to load
    let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref())
        .map_err(|e| ApiError::Internal(format!("Failed to create spiral snapshot: {}", e)))?;
    
    // Load snapshot
    let snapshot = spiral.load_snapshot(&request.snapshot_id)
        .map_err(|e| ApiError::NotFound(format!("Failed to load snapshot: {}", e)))?
        .ok_or_else(|| ApiError::NotFound(format!("Snapshot {} not found", request.snapshot_id)))?;
    
    // Create Solve-Coagula operator
    let mut solver = SolveCoagula::new(0.8, 1e-6, 1000);
    
    // Process the snapshot
    let coords_vec = snapshot.coords.iter().flat_map(|c| vec![c.x, c.y, c.z, c.w, c.u]).collect::<Vec<f64>>();
    let result = solver.apply(coords_vec)
        .map_err(|e| ApiError::Processing(format!("Solve-Coagula failed: {}", e)))?;
    
    // Create TIC
    let crystallizer = TICCrystallizer::new();
    let tic = crystallizer.crystallize(&result)
        .map_err(|e| ApiError::Processing(format!("TIC crystallization failed: {}", e)))?;
    
    Ok(Json(SolveResponse {
        tic_id: tic.id.clone(),
        status: if result.converged { "converged" } else { "max_iterations" }.to_string(),
        steps: result.iterations,
    }))
}

/// Validate a snapshot using Proof-of-Resonance
async fn validate(
    State(state): State<AppState>,
    Path(snapshot_id): Path<String>,
) -> Result<Json<ValidateResponse>> {
    // Create spiral snapshot handler to load
    let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref())
        .map_err(|e| ApiError::Internal(format!("Failed to create spiral snapshot: {}", e)))?;
    
    // Load snapshot
    let snapshot = spiral.load_snapshot(&snapshot_id)
        .map_err(|e| ApiError::NotFound(format!("Failed to load snapshot: {}", e)))?
        .ok_or_else(|| ApiError::NotFound(format!("Snapshot {} not found", snapshot_id)))?;
    
    // Parse PoR value
    let por: f64 = snapshot.por.parse().unwrap_or(0.0);
    let valid = por > 0.5; // Threshold for validity
    
    Ok(Json(ValidateResponse {
        snapshot_id,
        overall_valid: valid,
        resonance: ResonanceMetrics {
            fft_resonance: por,
            spectral_gap: 0.0, // TODO: Implement
            phase_coherence: snapshot.phase,
        },
        stability: StabilityMetrics {
            convergence_rate: 0.0, // TODO: Implement
            entropy: 0.0, // TODO: Implement
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ApiConfig;
    
    #[tokio::test]
    async fn test_solve_basic() {
        let config = ApiConfig::default();
        let state = AppState::new(config).await.unwrap();
        
        // Create spiral snapshot handler
        let spiral = SpiralSnapshot::new(state.spiral_config.as_ref().clone(), state.store_path.as_ref()).unwrap();
        
        // Create and store a test snapshot
        let normalized = vec![1.0, 2.0, 3.0];
        let snapshot = spiral.create_snapshot(
            normalized,
            "test_seed",
            "text",
        ).unwrap();
        
        let _snapshot_path = spiral.save_snapshot(&snapshot).unwrap();
        let snapshot_id = snapshot.id.clone();
        
        let request = SolveRequest {
            snapshot_id,
        };
        
        let result = solve(State(state), Json(request)).await;
        assert!(result.is_ok());
    }
}
