/// Merkaba Gate API endpoints
use axum::{
    extract::{Query, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

use crate::{error::ApiError, AppState, Result};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/gate/merkaba", post(evaluate_merkaba_gate))
        .route("/gate/merkaba/status", get(get_merkaba_status))
        .route("/gate/merkaba/audit", get(get_audit_log))
        .route("/gate/merkaba/calibrate", post(calibrate_thresholds))
}

/// Evaluate TIC candidate through Merkaba Gate
#[derive(Debug, Deserialize)]
struct MerkabaGateRequest {
    snapshot_id: String,
    tic_candidate_id: String,
    #[serde(default)]
    params: Option<GateParams>,
}

#[derive(Debug, Deserialize)]
struct GateParams {
    epsilon: Option<f64>,
    phi_star: Option<f64>,
    eta: Option<f64>,
}

#[derive(Debug, Serialize)]
struct MerkabaGateResponse {
    gate_id: String,
    snapshot_id: String,
    tic_candidate_id: String,
    checks: GateChecks,
    decision: GateDecision,
    timestamp: String,
    ledger_block_id: Option<String>,
}

#[derive(Debug, Serialize)]
struct GateChecks {
    por: String,
    delta_pi: f64,
    phi: f64,
    delta_v: f64,
    mci: Option<f64>,
}

#[derive(Debug, Serialize)]
struct GateDecision {
    commit: bool,
    reason: String,
}

async fn evaluate_merkaba_gate(
    State(_state): State<AppState>,
    Json(request): Json<MerkabaGateRequest>,
) -> Result<Json<MerkabaGateResponse>> {
    // TODO: Implement actual Merkaba Gate evaluation using mef-core
    // For now, return placeholder response with gate evaluation
    
    // Simulate gate checks
    let delta_pi = 0.0015; // Path invariance deviation
    let phi = 0.95; // Coherence measure
    let delta_v = -0.05; // Lyapunov stability (negative = stable)
    let mci = Some(0.98); // Mirror Consistency Index
    
    // Determine if gate passes (using default thresholds)
    let epsilon = request.params.as_ref()
        .and_then(|p| p.epsilon)
        .unwrap_or(0.02);
    let phi_star = request.params.as_ref()
        .and_then(|p| p.phi_star)
        .unwrap_or(0.9);
    let eta = request.params.as_ref()
        .and_then(|p| p.eta)
        .unwrap_or(0.95);
    
    let passes_pi = delta_pi < epsilon;
    let passes_phi = phi > phi_star;
    let passes_mci = mci.map(|m| m > eta).unwrap_or(true);
    let passes_lyapunov = delta_v < 0.0;
    
    let commit = passes_pi && passes_phi && passes_mci && passes_lyapunov;
    
    let reason = if commit {
        "All gate checks passed: PoR valid, ΔPI < ε, Φ > Φ*, MCI > η, ΔV < 0".to_string()
    } else {
        let mut failures = Vec::new();
        if !passes_pi {
            failures.push(format!("ΔPI={:.4} ≥ ε={:.4}", delta_pi, epsilon));
        }
        if !passes_phi {
            failures.push(format!("Φ={:.4} ≤ Φ*={:.4}", phi, phi_star));
        }
        if !passes_mci {
            failures.push(format!("MCI={:.4} ≤ η={:.4}", mci.unwrap(), eta));
        }
        if !passes_lyapunov {
            failures.push(format!("ΔV={:.4} ≥ 0", delta_v));
        }
        format!("Gate checks failed: {}", failures.join(", "))
    };
    
    let ledger_block_id = if commit {
        Some(format!("block_{}", uuid::Uuid::new_v4()))
    } else {
        None
    };
    
    Ok(Json(MerkabaGateResponse {
        gate_id: format!("gate_{}", uuid::Uuid::new_v4()),
        snapshot_id: request.snapshot_id,
        tic_candidate_id: request.tic_candidate_id,
        checks: GateChecks {
            por: "PASS".to_string(),
            delta_pi,
            phi,
            delta_v,
            mci,
        },
        decision: GateDecision {
            commit,
            reason,
        },
        timestamp: chrono::Utc::now().to_rfc3339(),
        ledger_block_id,
    }))
}

/// Get Merkaba Gate status and configuration
#[derive(Debug, Serialize)]
struct MerkabaStatusResponse {
    status: String,
    thresholds: ThresholdConfig,
    metatron_nodes: usize,
    state_history_length: usize,
    audit_path: String,
}

#[derive(Debug, Serialize)]
struct ThresholdConfig {
    epsilon: f64,
    phi_star: f64,
    eta: f64,
}

async fn get_merkaba_status(
    State(_state): State<AppState>,
) -> Result<Json<MerkabaStatusResponse>> {
    // TODO: Get actual gate status from MerkabaGate instance
    Ok(Json(MerkabaStatusResponse {
        status: "operational".to_string(),
        thresholds: ThresholdConfig {
            epsilon: 0.02,
            phi_star: 0.9,
            eta: 0.95,
        },
        metatron_nodes: 13,
        state_history_length: 0,
        audit_path: "store/merkaba_audit.jsonl".to_string(),
    }))
}

/// Get Merkaba Gate audit log
#[derive(Debug, Deserialize)]
struct AuditQuery {
    #[serde(default = "default_audit_limit")]
    limit: usize,
}

fn default_audit_limit() -> usize {
    100
}

#[derive(Debug, Serialize)]
struct AuditEntry {
    gate_id: String,
    snapshot_id: String,
    tic_candidate_id: String,
    decision: String,
    timestamp: String,
    checks: JsonValue,
}

#[derive(Debug, Serialize)]
struct AuditLogResponse {
    entries: Vec<AuditEntry>,
    total: usize,
}

async fn get_audit_log(
    State(_state): State<AppState>,
    Query(query): Query<AuditQuery>,
) -> Result<Json<AuditLogResponse>> {
    // TODO: Read actual audit log from file
    // For now, return empty audit log
    Ok(Json(AuditLogResponse {
        entries: vec![],
        total: 0,
    }))
}

/// Calibrate Merkaba Gate thresholds
#[derive(Debug, Deserialize)]
struct CalibrateRequest {
    #[serde(default)]
    epsilon: Option<f64>,
    #[serde(default)]
    phi_star: Option<f64>,
    #[serde(default)]
    eta: Option<f64>,
}

#[derive(Debug, Serialize)]
struct CalibrateResponse {
    status: String,
    updated: JsonValue,
    current: ThresholdConfig,
}

async fn calibrate_thresholds(
    State(_state): State<AppState>,
    Json(request): Json<CalibrateRequest>,
) -> Result<Json<CalibrateResponse>> {
    // TODO: Update actual gate thresholds in MerkabaGate instance
    // For now, just return acknowledgment
    
    let mut updated = serde_json::Map::new();
    
    if let Some(epsilon) = request.epsilon {
        updated.insert("epsilon".to_string(), serde_json::json!(epsilon));
    }
    if let Some(phi_star) = request.phi_star {
        updated.insert("phi_star".to_string(), serde_json::json!(phi_star));
    }
    if let Some(eta) = request.eta {
        updated.insert("eta".to_string(), serde_json::json!(eta));
    }
    
    Ok(Json(CalibrateResponse {
        status: "calibrated".to_string(),
        updated: serde_json::json!(updated),
        current: ThresholdConfig {
            epsilon: request.epsilon.unwrap_or(0.02),
            phi_star: request.phi_star.unwrap_or(0.9),
            eta: request.eta.unwrap_or(0.95),
        },
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::ApiConfig;

    async fn test_state() -> AppState {
        AppState::new(ApiConfig::default()).await.unwrap()
    }

    #[tokio::test]
    async fn test_evaluate_merkaba_gate() {
        let state = test_state().await;
        let request = MerkabaGateRequest {
            snapshot_id: "snap_123".to_string(),
            tic_candidate_id: "tic_456".to_string(),
            params: None,
        };
        let result = evaluate_merkaba_gate(State(state), Json(request)).await;
        assert!(result.is_ok());
        let response = result.unwrap().0;
        assert_eq!(response.snapshot_id, "snap_123");
        assert_eq!(response.tic_candidate_id, "tic_456");
        assert!(response.decision.commit); // Should pass with default good values
    }

    #[tokio::test]
    async fn test_get_merkaba_status() {
        let state = test_state().await;
        let result = get_merkaba_status(State(state)).await;
        assert!(result.is_ok());
        let response = result.unwrap().0;
        assert_eq!(response.status, "operational");
        assert_eq!(response.metatron_nodes, 13);
    }

    #[tokio::test]
    async fn test_get_audit_log() {
        let state = test_state().await;
        let query = AuditQuery { limit: 50 };
        let result = get_audit_log(State(state), Query(query)).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_calibrate_thresholds() {
        let state = test_state().await;
        let request = CalibrateRequest {
            epsilon: Some(0.015),
            phi_star: Some(0.92),
            eta: None,
        };
        let result = calibrate_thresholds(State(state), Json(request)).await;
        assert!(result.is_ok());
        let response = result.unwrap().0;
        assert_eq!(response.status, "calibrated");
        assert_eq!(response.current.epsilon, 0.015);
        assert_eq!(response.current.phi_star, 0.92);
    }
}
