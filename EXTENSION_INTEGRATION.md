# MEF Knowledge Engine - Integration Guide

**For Future Agent Iterations and Developers**

This guide provides step-by-step instructions for integrating the MEF Knowledge Engine extension with the core system and implementing the remaining functionality.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Phase 2: Configuration System](#phase-2-configuration-system)
3. [Phase 3: Pipeline Integration](#phase-3-pipeline-integration)
4. [Phase 4: API Routes](#phase-4-api-routes)
5. [Phase 5: Vector Backends](#phase-5-vector-backends)
6. [Testing Checklist](#testing-checklist)
7. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Current State

The extension scaffold is complete and tested:

```bash
# Build extension modules
cargo build --package mef-schemas \
            --package mef-knowledge \
            --package mef-router \
            --package mef-memory

# Run tests (51 tests, all passing)
cargo test --package mef-schemas \
           --package mef-knowledge \
           --package mef-router \
           --package mef-memory
```

### Verify No Core Impact

```bash
# Build entire workspace
cargo build --workspace

# Run all tests
cargo test --workspace

# Expected: All existing tests pass, no failures introduced
```

---

## Phase 2: Configuration System

### Step 1: Define Configuration Structure

Create `mef-knowledge/src/config.rs`:

```rust
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ExtensionConfig {
    #[serde(default)]
    pub knowledge: KnowledgeConfig,
    
    #[serde(default)]
    pub memory: MemoryConfig,
    
    #[serde(default)]
    pub router: RouterConfig,
    
    #[serde(default)]
    pub paths: PathsConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct KnowledgeConfig {
    #[serde(default)]
    pub enabled: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MemoryConfig {
    #[serde(default)]
    pub enabled: bool,
    
    pub path: Option<PathBuf>,
    
    #[serde(default = "default_dimension")]
    pub dimension: usize,
    
    #[serde(default = "default_metric")]
    pub metric: String,
    
    #[serde(default = "default_backend")]
    pub backend: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RouterConfig {
    #[serde(default)]
    pub mode: RouterMode,
    
    pub service_url: Option<String>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum RouterMode {
    InProc,
    Service,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PathsConfig {
    pub memory: Option<PathBuf>,
}

impl Default for ExtensionConfig {
    fn default() -> Self {
        Self {
            knowledge: KnowledgeConfig::default(),
            memory: MemoryConfig::default(),
            router: RouterConfig::default(),
            paths: PathsConfig::default(),
        }
    }
}

impl Default for KnowledgeConfig {
    fn default() -> Self {
        Self { enabled: false }
    }
}

impl Default for MemoryConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            path: None,
            dimension: 8,
            metric: "cosine".to_string(),
            backend: "in-memory".to_string(),
        }
    }
}

impl Default for RouterConfig {
    fn default() -> Self {
        Self {
            mode: RouterMode::InProc,
            service_url: None,
        }
    }
}

impl Default for PathsConfig {
    fn default() -> Self {
        Self { memory: None }
    }
}

fn default_dimension() -> usize { 8 }
fn default_metric() -> String { "cosine".to_string() }
fn default_backend() -> String { "in-memory".to_string() }
```

### Step 2: Add to lib.rs

```rust
// mef-knowledge/src/lib.rs
pub mod config;
pub use config::ExtensionConfig;
```

### Step 3: Create Config File

Create `config/extension.yaml`:

```yaml
knowledge:
  enabled: false  # Set to true to enable

memory:
  enabled: false  # Set to true to enable
  path: null      # Set to /path/to/index when enabling
  dimension: 8    # Fixed for MEF
  metric: cosine
  backend: in-memory

router:
  mode: inproc    # or 'service'
  service_url: null

paths:
  memory: null    # Same as memory.path
```

### Step 4: Load Configuration

In your application initialization:

```rust
use mef_knowledge::ExtensionConfig;
use std::fs;

let config_str = fs::read_to_string("config/extension.yaml")?;
let ext_config: ExtensionConfig = serde_yaml::from_str(&config_str)?;

// Initialize components based on config
if ext_config.memory.enabled {
    let memory_index = mef_memory::MemoryIndex::new(ext_config.memory.clone())?;
    // Store in application state
}
```

---

## Phase 3: Pipeline Integration

### Overview

Wire up the full derivation pipeline by calling into core modules:

```
Input → Acquisition → Spiral → PoR → Solve → Gate → TIC → Knowledge → Ledger
```

### Step 1: Define Core Module Interfaces

First, understand what the core modules expose:

```rust
// Check mef-spiral for:
pub fn create_snapshot(data: &[f64], seed: &[u8]) -> Snapshot;
pub fn compute_por(snapshot: &Snapshot) -> PorResult;

// Check mef-solvecoagula for:
pub fn iterate(initial: &State, route: &RouteSpec) -> IterationResult;

// Check mef-audit for:
pub fn evaluate_gate(result: &IterationResult) -> GateEvent;

// Check mef-tic for:
pub fn crystallize(result: &IterationResult) -> TicBlock;

// Check mef-ledger for:
pub fn append_block(tic: TicBlock) -> Result<u64, Error>;
```

### Step 2: Implement Pipeline in derivation.rs

Replace the placeholder in `mef-knowledge/src/derivation.rs`:

```rust
impl KnowledgeDerivation {
    pub async fn derive(&self, request: DeriveRequest) -> Result<DeriveResponse, DerivationError> {
        if !self.enabled {
            return Err(DerivationError::Disabled(
                "Knowledge derivation is disabled (knowledge.enabled=false)".to_string()
            ));
        }
        
        // Step 1: Normalize payload
        // TODO: Call mef_ingestion::normalize()
        // For now, assume payload is already normalized
        
        // Step 2: Derive seed
        let seed = derive_seed(
            &self.root_seed,  // Store root seed in struct (NEVER log/persist)
            &request.seed_path
        );
        
        // Step 3: Create spiral snapshot
        // TODO: Extract numeric data from payload
        // let data = extract_features(&request.payload)?;
        // let snapshot = mef_spiral::create_snapshot(&data, &seed)?;
        
        // Step 4: Compute PoR
        // let por = mef_spiral::compute_por(&snapshot)?;
        // if por.status != PorStatus::Valid {
        //     return Err(DerivationError::PorFailed(...));
        // }
        
        // Step 5: Select route
        let adapter = MetatronAdapter::default();
        let route = adapter.get_route(&request.seed_path, None).await?;
        
        // Step 6: Execute Solve-Coagula
        // TODO: Get initial state from snapshot
        // let initial_state = snapshot.to_state();
        // let result = mef_solvecoagula::iterate(&initial_state, &route)?;
        
        // Step 7: Evaluate gate
        // let gate_event = mef_audit::evaluate_gate(&result)?;
        // if !gate_event.is_fire() {
        //     return Err(DerivationError::GateHeld(gate_event.decision.reason));
        // }
        
        // Step 8: Crystallize TIC
        // let tic = mef_tic::crystallize(&result)?;
        
        // Step 9: Build knowledge object
        // let mef_id = compute_mef_id(&tic, &route.route_id, &request.seed_path)?;
        // let knowledge = KnowledgeObject::new(...);
        
        // Step 10: Append to ledger
        // let block_num = mef_ledger::append_block(tic)?;
        
        // For now, return placeholder
        Ok(placeholder_response())
    }
}
```

### Step 3: Add Error Handling

```rust
// Handle each failure mode appropriately
match mef_spiral::compute_por(&snapshot) {
    Ok(por) if por.status == PorStatus::Valid => {
        // Continue
    }
    Ok(por) => {
        return Err(DerivationError::PorFailed(
            format!("PoR invalid: {:?}", por.metrics)
        ));
    }
    Err(e) => {
        return Err(DerivationError::SpiralFailed(e.to_string()));
    }
}
```

### Step 4: Test End-to-End

```rust
#[tokio::test]
async fn test_full_derivation_pipeline() {
    let config = ExtensionConfig {
        knowledge: KnowledgeConfig { enabled: true },
        ..Default::default()
    };
    
    let derivation = KnowledgeDerivation::new(config);
    
    let request = DeriveRequest {
        payload: json!({"test": "data"}),
        seed_path: "MEF/test/spiral/0001".to_string(),
        domain: Some("test".to_string()),
    };
    
    let result = derivation.derive(request).await;
    assert!(result.is_ok());
    
    let response = result.unwrap();
    assert!(!response.mef_id.is_empty());
    assert_eq!(response.block > 0);
}
```

---

## Phase 4: API Routes

### Step 1: Create Routes Module

Create `mef-api/src/routes/knowledge.rs`:

```rust
use axum::{
    extract::State,
    http::StatusCode,
    Json,
    response::{IntoResponse, Response},
};
use mef_knowledge::{DeriveRequest, DeriveResponse, KnowledgeDerivation};
use mef_schemas::KnowledgeObject;
use serde_json::json;

// Derive knowledge endpoint
pub async fn derive_handler(
    State(derivation): State<KnowledgeDerivation>,
    Json(request): Json<DeriveRequest>,
) -> Result<Json<DeriveResponse>, AppError> {
    let response = derivation
        .derive(request)
        .await
        .map_err(|e| AppError::Derivation(e.to_string()))?;
    
    Ok(Json(response))
}

// Validate knowledge endpoint
pub async fn validate_handler(
    Json(knowledge): Json<KnowledgeObject>,
) -> Result<Json<serde_json::Value>, AppError> {
    mef_knowledge::KnowledgeInference::validate(&knowledge)
        .map_err(|e| AppError::Validation(e.to_string()))?;
    
    Ok(Json(json!({
        "valid": true,
        "mef_id": knowledge.mef_id,
    })))
}

// Project knowledge endpoint
pub async fn project_handler(
    Json(request): Json<ProjectRequest>,
) -> Result<Json<serde_json::Value>, AppError> {
    let projection = mef_knowledge::KnowledgeInference::project(
        &request.knowledge,
        request.mode,
    )
    .map_err(|e| AppError::Projection(e.to_string()))?;
    
    Ok(Json(projection))
}

#[derive(Debug, serde::Deserialize)]
pub struct ProjectRequest {
    pub knowledge: KnowledgeObject,
    pub mode: mef_knowledge::ProjectionMode,
}

// Error types
#[derive(Debug)]
pub enum AppError {
    Derivation(String),
    Validation(String),
    Projection(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::Derivation(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::Projection(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg),
        };
        
        let body = Json(json!({
            "error": message,
        }));
        
        (status, body).into_response()
    }
}
```

### Step 2: Register Routes

In `mef-api/src/main.rs` or `lib.rs`:

```rust
use axum::{Router, routing::post};

pub fn create_app(config: AppConfig) -> Router {
    let mut app = Router::new()
        // Existing core routes
        .route("/healthz", get(health_check))
        // ... other core routes ...
        ;
    
    // Add extension routes if enabled
    if config.extension.knowledge.enabled {
        app = app.nest("/knowledge", knowledge_routes());
    }
    
    if config.extension.memory.enabled {
        app = app.nest("/memory", memory_routes());
    }
    
    if config.extension.router.enabled {
        app = app.nest("/router", router_routes());
    }
    
    app
}

fn knowledge_routes() -> Router {
    Router::new()
        .route("/derive", post(derive_handler))
        .route("/validate", post(validate_handler))
        .route("/project", post(project_handler))
}

fn memory_routes() -> Router {
    Router::new()
        .route("/upsert", post(memory_upsert_handler))
        .route("/search", post(memory_search_handler))
        .route("/stats", get(memory_stats_handler))
}

fn router_routes() -> Router {
    Router::new()
        .route("/select", post(router_select_handler))
}
```

### Step 3: Test API Routes

```bash
# Start the API server
cargo run --release --package mef-api

# Test knowledge derivation
curl -X POST http://localhost:8000/knowledge/derive \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {"test": "data"},
    "seed_path": "MEF/test/spiral/0001",
    "domain": "test"
  }'

# Test memory search
curl -X POST http://localhost:8000/memory/search \
  -H "Content-Type: application/json" \
  -d '{
    "query_vector8": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "top_k": 5
  }'
```

---

## Phase 5: Vector Backends

### Step 1: FAISS Backend (Optional)

Add to `mef-memory/Cargo.toml`:

```toml
[dependencies]
# ... existing ...

[target.'cfg(not(target_env = "msvc"))'.dependencies]
faiss = { version = "0.11", optional = true }

[features]
default = []
faiss-backend = ["faiss"]
```

Implement in `mef-memory/src/backends/faiss.rs`:

```rust
#[cfg(feature = "faiss-backend")]
pub struct FaissBackend {
    index: faiss::Index,
    dimension: usize,
}

#[cfg(feature = "faiss-backend")]
impl FaissBackend {
    pub fn new(dimension: usize) -> Result<Self, String> {
        let index = faiss::Index::new_flat(dimension, faiss::MetricType::InnerProduct)
            .map_err(|e| e.to_string())?;
        
        Ok(Self { index, dimension })
    }
}

#[cfg(feature = "faiss-backend")]
#[async_trait]
impl VectorBackend for FaissBackend {
    async fn upsert(&mut self, item: MemoryItem) -> Result<(), String> {
        // Convert to FAISS format
        let vector: Vec<f32> = item.vector8.iter().map(|&x| x as f32).collect();
        
        self.index.add(&[vector.as_slice()])
            .map_err(|e| e.to_string())?;
        
        Ok(())
    }
    
    async fn search(
        &self,
        query: &[f64],
        top_k: usize,
        _filters: Option<serde_json::Value>,
    ) -> Result<Vec<(String, f64)>, String> {
        let query_f32: Vec<f32> = query.iter().map(|&x| x as f32).collect();
        
        let result = self.index.search(&[query_f32.as_slice()], top_k)
            .map_err(|e| e.to_string())?;
        
        // Convert result to (id, distance) pairs
        // Note: You'll need to store IDs separately
        // TODO: Implement ID mapping
        
        Ok(Vec::new())
    }
    
    // ... implement other methods
}
```

### Step 2: Select Backend at Runtime

```rust
use mef_memory::backends::{InMemoryBackend, VectorBackend};

fn create_backend(config: &MemoryConfig) -> Result<Box<dyn VectorBackend>, String> {
    match config.backend.as_str() {
        "in-memory" => Ok(Box::new(InMemoryBackend::new())),
        
        #[cfg(feature = "faiss-backend")]
        "faiss" => Ok(Box::new(FaissBackend::new(config.dimension)?)),
        
        backend => Err(format!("Unknown backend: {}", backend)),
    }
}
```

---

## Testing Checklist

### Unit Tests

- [ ] All 51 extension tests pass
- [ ] All core tests still pass
- [ ] New pipeline integration tests added

### Integration Tests

- [ ] End-to-end derivation flow works
- [ ] Features disabled → no impact on core
- [ ] Features enabled → extension functional

### Determinism Tests

- [ ] Same input + same seed → same output (run 10 times)
- [ ] Route selection deterministic
- [ ] Canonical JSON stable across platforms

### Performance Tests

- [ ] No regression in core benchmarks
- [ ] Extension overhead < 1% when disabled
- [ ] Memory usage within expected bounds

### Security Tests

- [ ] Root seeds never logged
- [ ] Root seeds never persisted
- [ ] Content hashes match expected values

---

## Troubleshooting

### Build Errors

**Problem:** `unresolved import mef_schemas::...`

**Solution:** Check that types are re-exported in `mef-schemas/src/lib.rs`:

```rust
pub use route_spec::{RouteSpec, OperatorSlot};
pub use memory_item::{MemoryItem, SpectralSignature, PorStatus};
// ... etc
```

**Problem:** `conflicting implementations of trait VectorBackend`

**Solution:** Use feature flags to gate conflicting implementations.

### Runtime Errors

**Problem:** "Memory index is disabled"

**Solution:** Check config file has `memory.enabled: true` and `memory.path` is set.

**Problem:** "Route service unavailable"

**Solution:** Either set `router.mode: inproc` or provide `router.service_url`.

### Test Failures

**Problem:** "Assertion failed: same input produced different output"

**Solution:** Check for sources of non-determinism:
- Random number generation without fixed seed
- Timestamp usage in critical paths
- Unordered map iteration

**Problem:** "Core tests failing after extension added"

**Solution:** Extension must not modify core. Check:
- No changes to core module files
- All config defaults are false/disabled
- Feature flags properly gating functionality

---

## Additional Resources

- [ARCHITECTURE_EXTENSION.md](./ARCHITECTURE_EXTENSION.md) - Detailed architecture
- [SPEC-006 PDF](./Infinity-Ledger_Expansion_1-4.pdf) - Original blueprint
- [Core README](./README.md) - Core system documentation

---

**Last Updated:** October 2025  
**Maintained By:** MEF-Core Extension Team
