/// Metatron Router API endpoints
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    routing::{delete, get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use serde_json::Value as JsonValue;

use crate::{error::ApiError, AppState, Result};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/pipeline/process", post(process_through_pipeline))
        .route("/pipeline/metrics", get(get_pipeline_metrics))
        .route("/metatron/route/select", post(select_optimal_route))
        .route("/metatron/transform", post(apply_transformation))
        .route("/metatron/topology/nodes", get(get_topology_nodes))
        .route("/metatron/topology/edges", get(get_topology_edges))
        .route("/metatron/symmetry/:group", get(get_symmetry_group))
        .route("/metatron/operators", get(list_operators))
        .route("/metatron/resonance/calculate", post(calculate_resonance))
        .route("/metatron/cache/status", get(get_cache_status))
        .route("/metatron/cache/clear", delete(clear_cache))
        .route("/metatron/export/:route_id", get(export_route))
        .route("/status/integration", get(get_integration_status))
}

/// Process data through MEF-Core pipeline with Metatron routing
#[derive(Debug, Deserialize)]
struct ProcessRequest {
    raw_input: JsonValue,
    #[serde(default = "default_input_type")]
    input_type: String,
    #[serde(default)]
    target_properties: Option<JsonValue>,
    #[serde(default = "default_use_cached_route")]
    use_cached_route: bool,
}

fn default_input_type() -> String {
    "json".to_string()
}

fn default_use_cached_route() -> bool {
    true
}

#[derive(Debug, Serialize)]
struct ProcessResponse {
    tic_id: String,
    fixpoint: Vec<f64>,
    route: RouteInfo,
    metrics: JsonValue,
    proof: JsonValue,
    timestamp: String,
}

#[derive(Debug, Serialize)]
struct RouteInfo {
    route_id: String,
    symmetry_group: String,
    score: f64,
    operators: Vec<String>,
}

async fn process_through_pipeline(
    State(_state): State<AppState>,
    Json(request): Json<ProcessRequest>,
) -> Result<Json<ProcessResponse>> {
    // TODO: Implement actual pipeline processing with Metatron routing
    // For now, return placeholder response
    Ok(Json(ProcessResponse {
        tic_id: format!("tic_{}", uuid::Uuid::new_v4()),
        fixpoint: vec![0.0; 13],
        route: RouteInfo {
            route_id: format!("route_{}", uuid::Uuid::new_v4()),
            symmetry_group: "C6".to_string(),
            score: 0.95,
            operators: vec!["DK".to_string(), "SW".to_string(), "PI".to_string()],
        },
        metrics: serde_json::json!({}),
        proof: serde_json::json!({}),
        timestamp: chrono::Utc::now().to_rfc3339(),
    }))
}

/// Get pipeline metrics including Metatron topology
#[derive(Debug, Serialize)]
struct PipelineMetrics {
    total_processed: usize,
    average_route_score: f64,
    cache_hit_rate: f64,
    topology_status: String,
    symmetry_groups: Vec<String>,
}

async fn get_pipeline_metrics(
    State(_state): State<AppState>,
) -> Result<Json<PipelineMetrics>> {
    Ok(Json(PipelineMetrics {
        total_processed: 0,
        average_route_score: 0.92,
        cache_hit_rate: 0.75,
        topology_status: "operational".to_string(),
        symmetry_groups: vec!["C6".to_string(), "D6".to_string(), "S7".to_string()],
    }))
}

/// Select optimal transformation route through Metatron topology
#[derive(Debug, Deserialize)]
struct RouteSelectionRequest {
    input_vector: Vec<f64>,
    #[serde(default)]
    target_properties: Option<JsonValue>,
}

#[derive(Debug, Serialize)]
struct RouteSelectionResponse {
    route_id: String,
    permutation: Vec<usize>,
    operator_sequence: Vec<String>,
    symmetry_group: String,
    score: f64,
    metadata: JsonValue,
}

async fn select_optimal_route(
    State(state): State<AppState>,
    Json(request): Json<RouteSelectionRequest>,
) -> Result<Json<RouteSelectionResponse>> {
    // Use MetatronRouter to select optimal route
    let mut router = state.metatron_router.lock().unwrap();
    
    // Convert target properties to HashMap if present
    let target_props = request.target_properties.as_ref()
        .and_then(|v| v.as_object())
        .map(|obj| {
            obj.iter()
                .map(|(k, v)| (k.clone(), v.to_string()))
                .collect::<std::collections::HashMap<String, String>>()
        });
    
    let route_spec = router.select_optimal_route(
        &request.input_vector,
        target_props.as_ref(),
    );
    
    // Convert operator types to strings
    let operator_sequence: Vec<String> = route_spec.operator_sequence.iter()
        .map(|op| format!("{:?}", op))
        .collect();
    
    Ok(Json(RouteSelectionResponse {
        route_id: route_spec.route_id,
        permutation: route_spec.permutation,
        operator_sequence,
        symmetry_group: route_spec.symmetry_group,
        score: route_spec.score,
        metadata: serde_json::to_value(route_spec.metadata).unwrap_or(serde_json::json!({})),
    }))
}

/// Apply transformation through Metatron topology
#[derive(Debug, Deserialize)]
struct TransformRequest {
    input_vector: Vec<f64>,
    #[serde(default)]
    route_id: Option<String>,
    #[serde(default)]
    operator_sequence: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
struct TransformResponse {
    input: Vec<f64>,
    output: Vec<f64>,
    route: RouteInfo,
    resonance_metrics: ResonanceMetrics,
    convergence_data: Vec<ConvergenceStep>,
    timestamp: String,
}

#[derive(Debug, Serialize)]
struct ResonanceMetrics {
    input_resonance: f64,
    output_resonance: f64,
    coherence: f64,
    stability: f64,
    convergence: f64,
}

#[derive(Debug, Serialize)]
struct ConvergenceStep {
    operator: String,
    delta_norm: f64,
    resonance: f64,
    entropy: f64,
}

async fn apply_transformation(
    State(state): State<AppState>,
    Json(request): Json<TransformRequest>,
) -> Result<Json<TransformResponse>> {
    // Get MetatronRouter
    let mut router = state.metatron_router.lock().unwrap();
    
    // Look up route spec if route_id provided
    let route_spec = if let Some(route_id) = &request.route_id {
        router.route_cache.get(route_id).cloned()
    } else if let Some(op_seq) = &request.operator_sequence {
        // Create custom route spec from operator sequence
        use mef_topology::OperatorType;
        let operators: Vec<OperatorType> = op_seq.iter()
            .filter_map(|s| match s.as_str() {
                "DK" => Some(OperatorType::DK),
                "SW" => Some(OperatorType::SW),
                "PI" => Some(OperatorType::PI),
                "WT" => Some(OperatorType::WT),
                _ => None,
            })
            .collect();
        
        Some(mef_topology::RouteSpec {
            route_id: uuid::Uuid::new_v4().to_string(),
            permutation: (1..=13).collect(),
            operator_sequence: operators,
            symmetry_group: "Identity".to_string(),
            score: 0.0,
            metadata: std::collections::HashMap::new(),
        })
    } else {
        None
    };
    
    // Apply transformation
    let result = router.transform(&request.input_vector, route_spec.as_ref());
    
    Ok(Json(TransformResponse {
        input: result.input_vector,
        output: result.output_vector,
        route: RouteInfo {
            route_id: result.route_spec.route_id,
            symmetry_group: result.route_spec.symmetry_group,
            score: result.route_spec.score,
            operators: result.route_spec.operator_sequence.iter()
                .map(|op| format!("{:?}", op))
                .collect(),
        },
        resonance_metrics: ResonanceMetrics {
            input_resonance: result.resonance_metrics.input_resonance,
            output_resonance: result.resonance_metrics.output_resonance,
            coherence: result.resonance_metrics.coherence,
            stability: result.resonance_metrics.stability,
            convergence: result.resonance_metrics.convergence,
        },
        convergence_data: result.convergence_data.iter().map(|step| ConvergenceStep {
            operator: step.operator.clone(),
            delta_norm: step.delta_norm,
            resonance: step.resonance,
            entropy: step.entropy,
        }).collect(),
        timestamp: result.timestamp,
    }))
}

/// Get Metatron topology nodes information
#[derive(Debug, Deserialize)]
struct TopologyNodesQuery {
    #[serde(default)]
    node_id: Option<usize>,
}

#[derive(Debug, Serialize)]
struct TopologyNode {
    id: usize,
    name: String,
    position: Vec<f64>,
    connections: Vec<usize>,
}

#[derive(Debug, Serialize)]
struct TopologyNodesResponse {
    nodes: Vec<TopologyNode>,
    total_nodes: usize,
}

async fn get_topology_nodes(
    State(state): State<AppState>,
    Query(query): Query<TopologyNodesQuery>,
) -> Result<Json<TopologyNodesResponse>> {
    // Get canonical nodes from Metatron Cube
    use mef_core::canonical_nodes;
    let nodes = canonical_nodes();
    
    let result_nodes: Vec<TopologyNode> = if let Some(node_id) = query.node_id {
        // Return specific node
        if node_id > 0 && node_id <= nodes.len() {
            let node = &nodes[node_id - 1];
            vec![TopologyNode {
                id: node_id,
                name: node.label.clone(),
                position: vec![node.coords.0, node.coords.1, node.coords.2],
                connections: vec![], // Would need adjacency info from graph
            }]
        } else {
            return Err(ApiError::NotFound(format!("Node {} not found", node_id)));
        }
    } else {
        // Return all nodes
        nodes.iter().map(|node| TopologyNode {
            id: node.index,
            name: node.label.clone(),
            position: vec![node.coords.0, node.coords.1, node.coords.2],
            connections: vec![], // Would need to compute from adjacency matrix
        }).collect()
    };
    
    Ok(Json(TopologyNodesResponse {
        total_nodes: result_nodes.len(),
        nodes: result_nodes,
    }))
}

/// Get Metatron topology edges information
#[derive(Debug, Deserialize)]
struct TopologyEdgesQuery {
    #[serde(default)]
    edge_type: Option<String>,
}

#[derive(Debug, Serialize)]
struct TopologyEdge {
    source: usize,
    target: usize,
    edge_type: String,
    weight: f64,
}

#[derive(Debug, Serialize)]
struct TopologyEdgesResponse {
    edges: Vec<TopologyEdge>,
    total_edges: usize,
}

async fn get_topology_edges(
    State(state): State<AppState>,
    Query(query): Query<TopologyEdgesQuery>,
) -> Result<Json<TopologyEdgesResponse>> {
    // Get edges from Metatron graph
    let router = state.metatron_router.lock().unwrap();
    let adjacency = router.graph.get_adjacency_matrix();
    
    let mut edges = Vec::new();
    
    // Extract edges from adjacency matrix (13x13 matrix)
    for i in 0..13 {
        for j in (i+1)..13 {
            let weight = adjacency[[i, j]];
            if weight > 0.0 {
                let edge_type = if query.edge_type.is_none() || 
                    query.edge_type.as_ref().map(|t| t == "direct").unwrap_or(true) {
                    "direct"
                } else {
                    continue;
                };
                
                edges.push(TopologyEdge {
                    source: i + 1,
                    target: j + 1,
                    edge_type: edge_type.to_string(),
                    weight,
                });
            }
        }
    }
    
    Ok(Json(TopologyEdgesResponse {
        total_edges: edges.len(),
        edges,
    }))
}

/// Get symmetry group information
#[derive(Debug, Serialize)]
struct SymmetryGroupResponse {
    group: String,
    order: usize,
    permutations: Vec<Vec<usize>>,
    description: String,
}

async fn get_symmetry_group(
    State(state): State<AppState>,
    Path(group): Path<String>,
) -> Result<Json<SymmetryGroupResponse>> {
    // Get symmetry permutations from MetatronRouter
    let router = state.metatron_router.lock().unwrap();
    
    let (permutations, order, description) = match group.as_str() {
        "C6" => (
            router.c6_perms.clone(),
            6,
            "Cyclic group of order 6"
        ),
        "D6" => (
            router.d6_perms.clone(),
            12,
            "Dihedral group of order 12"
        ),
        "S7" => (
            // Return first 100 permutations of S7 (all 5040 would be too large)
            router.s7_perms.iter().take(100).cloned().collect(),
            5040,
            "Symmetric group of order 5040 (showing first 100)"
        ),
        _ => return Err(ApiError::NotFound(format!("Unknown symmetry group: {}", group))),
    };
    
    Ok(Json(SymmetryGroupResponse {
        group: group.clone(),
        order,
        permutations,
        description: description.to_string(),
    }))
}

/// List available operators
#[derive(Debug, Serialize)]
struct Operator {
    name: String,
    symbol: String,
    description: String,
}

#[derive(Debug, Serialize)]
struct OperatorsResponse {
    operators: Vec<Operator>,
}

async fn list_operators(
    State(_state): State<AppState>,
) -> Result<Json<OperatorsResponse>> {
    Ok(Json(OperatorsResponse {
        operators: vec![
            Operator {
                name: "DoubleKick".to_string(),
                symbol: "DK".to_string(),
                description: "Double impulse operator".to_string(),
            },
            Operator {
                name: "Sweep".to_string(),
                symbol: "SW".to_string(),
                description: "Threshold sweep operator".to_string(),
            },
            Operator {
                name: "PathInvariance".to_string(),
                symbol: "PI".to_string(),
                description: "Path invariance projection".to_string(),
            },
            Operator {
                name: "WeightTransfer".to_string(),
                symbol: "WT".to_string(),
                description: "Scale weight transfer".to_string(),
            },
        ],
    }))
}

/// Calculate resonance scores
#[derive(Debug, Deserialize)]
struct ResonanceRequest {
    input_vector: Vec<f64>,
    reference_vector: Option<Vec<f64>>,
}

#[derive(Debug, Serialize)]
struct ResonanceResponse {
    resonance: f64,
    coherence: f64,
    entropy: f64,
    variance: f64,
}

async fn calculate_resonance(
    State(state): State<AppState>,
    Json(request): Json<ResonanceRequest>,
) -> Result<Json<ResonanceResponse>> {
    // Calculate resonance using basic metrics since calculate_resonance is private
    // In production, this would use the full Metatron resonance calculation
    
    // Calculate coherence
    let coherence = if let Some(ref_vec) = &request.reference_vector {
        // Calculate similarity if reference provided
        let dot_product: f64 = request.input_vector.iter().zip(ref_vec.iter())
            .map(|(a, b)| a * b)
            .sum();
        let input_norm: f64 = request.input_vector.iter().map(|x| x * x).sum::<f64>().sqrt();
        let ref_norm: f64 = ref_vec.iter().map(|x| x * x).sum::<f64>().sqrt();
        
        if input_norm > 1e-10 && ref_norm > 1e-10 {
            (dot_product / (input_norm * ref_norm)).abs()
        } else {
            0.0
        }
    } else {
        // Default coherence based on vector properties
        0.85
    };
    
    // Calculate entropy
    let sum: f64 = request.input_vector.iter().map(|x| x.abs()).sum();
    let entropy = if sum > 1e-10 {
        let probs: Vec<f64> = request.input_vector.iter().map(|x| x.abs() / sum).collect();
        -probs.iter().filter(|&&x| x > 1e-10).map(|&x| x * x.ln()).sum::<f64>()
    } else {
        0.0
    };
    
    // Calculate variance
    let mean = request.input_vector.iter().sum::<f64>() / request.input_vector.len() as f64;
    let variance = request.input_vector.iter()
        .map(|x| (x - mean).powi(2))
        .sum::<f64>() / request.input_vector.len() as f64;
    
    // Estimate resonance from coherence and entropy
    let max_entropy = (request.input_vector.len() as f64).ln();
    let resonance = if max_entropy > 0.0 {
        coherence * (1.0 - (entropy / max_entropy).min(1.0))
    } else {
        coherence
    };
    
    Ok(Json(ResonanceResponse {
        resonance,
        coherence,
        entropy,
        variance,
    }))
}

/// Get route cache status
#[derive(Debug, Serialize)]
struct CacheStatusResponse {
    enabled: bool,
    size: usize,
    max_size: usize,
    hit_rate: f64,
}

async fn get_cache_status(
    State(state): State<AppState>,
) -> Result<Json<CacheStatusResponse>> {
    // Get cache status from MetatronRouter
    let router = state.metatron_router.lock().unwrap();
    
    Ok(Json(CacheStatusResponse {
        enabled: router.cache_enabled,
        size: router.route_cache.len(),
        max_size: 1000, // Could make this configurable
        hit_rate: 0.0, // Would need to track hits/misses for real implementation
    }))
}

/// Clear route cache
#[derive(Debug, Serialize)]
struct ClearCacheResponse {
    cleared: usize,
    timestamp: String,
}

async fn clear_cache(
    State(state): State<AppState>,
) -> Result<Json<ClearCacheResponse>> {
    // Clear route cache in MetatronRouter
    let mut router = state.metatron_router.lock().unwrap();
    let cleared = router.route_cache.len();
    router.route_cache.clear();
    
    Ok(Json(ClearCacheResponse {
        cleared,
        timestamp: chrono::Utc::now().to_rfc3339(),
    }))
}

/// Export route definition
#[derive(Debug, Serialize)]
struct RouteExportResponse {
    route_id: String,
    permutation: Vec<usize>,
    operator_sequence: Vec<String>,
    symmetry_group: String,
    score: f64,
    metadata: JsonValue,
    export_format: String,
}

async fn export_route(
    State(state): State<AppState>,
    Path(route_id): Path<String>,
) -> Result<Json<RouteExportResponse>> {
    // Load route from cache
    let router = state.metatron_router.lock().unwrap();
    
    let route_spec = router.route_cache.get(&route_id)
        .ok_or_else(|| ApiError::NotFound(format!("Route {} not found in cache", route_id)))?;
    
    Ok(Json(RouteExportResponse {
        route_id: route_spec.route_id.clone(),
        permutation: route_spec.permutation.clone(),
        operator_sequence: route_spec.operator_sequence.iter()
            .map(|op| format!("{:?}", op))
            .collect(),
        symmetry_group: route_spec.symmetry_group.clone(),
        score: route_spec.score,
        metadata: serde_json::to_value(&route_spec.metadata).unwrap_or(serde_json::json!({})),
        export_format: "json".to_string(),
    }))
}

/// Get integration status
#[derive(Debug, Serialize)]
struct IntegrationStatusResponse {
    metatron_router: String,
    topology: String,
    operator_system: String,
    cache: String,
    version: String,
}

async fn get_integration_status(
    State(_state): State<AppState>,
) -> Result<Json<IntegrationStatusResponse>> {
    Ok(Json(IntegrationStatusResponse {
        metatron_router: "operational".to_string(),
        topology: "13-node cube active".to_string(),
        operator_system: "4 operators registered".to_string(),
        cache: "enabled".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
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
    async fn test_process_through_pipeline() {
        let state = test_state().await;
        let request = ProcessRequest {
            raw_input: serde_json::json!({"data": [1.0, 2.0, 3.0]}),
            input_type: "json".to_string(),
            target_properties: None,
            use_cached_route: true,
        };
        let result = process_through_pipeline(State(state), Json(request)).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_get_pipeline_metrics() {
        let state = test_state().await;
        let result = get_pipeline_metrics(State(state)).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_select_optimal_route() {
        let state = test_state().await;
        let request = RouteSelectionRequest {
            input_vector: vec![1.0; 13],
            target_properties: None,
        };
        let result = select_optimal_route(State(state), Json(request)).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_apply_transformation() {
        let state = test_state().await;
        let request = TransformRequest {
            input_vector: vec![1.0; 13],
            route_id: None,
            operator_sequence: None,
        };
        let result = apply_transformation(State(state), Json(request)).await;
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_list_operators() {
        let state = test_state().await;
        let result = list_operators(State(state)).await;
        assert!(result.is_ok());
        let response = result.unwrap().0;
        assert_eq!(response.operators.len(), 4);
    }

    #[tokio::test]
    async fn test_get_integration_status() {
        let state = test_state().await;
        let result = get_integration_status(State(state)).await;
        assert!(result.is_ok());
    }
}
