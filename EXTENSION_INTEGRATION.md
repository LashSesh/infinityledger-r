# MEF Knowledge Engine Extension - Integration Guide

## Overview

This document provides step-by-step instructions for Phase 2 integration of the MEF Knowledge Engine extension into the MEF-Core system. The extension scaffold is production-ready; this guide covers wiring it to core modules, configuration, and API endpoints.

## Prerequisites

- Phase 1 scaffold complete (mef-schemas, mef-knowledge, mef-memory, mef-router)
- All 47 tests passing
- Workspace builds successfully
- No modifications to core modules

## Phase 2 Integration Steps

### Step 1: Configuration System

#### 1.1 Create Configuration Schema

Create `config/extension.yaml`:

```yaml
mef:
  extension:
    # Knowledge processing
    knowledge:
      enabled: false  # Default OFF
      inference:
        threshold: 0.5
        max_iterations: 100
      derivation:
        root_seed_env: "MEF_ROOT_SEED"  # Environment variable for root seed
        default_path_prefix: "MEF"
    
    # Vector memory
    memory:
      enabled: false  # Default OFF
      backend: inmemory  # Options: inmemory, faiss, hnsw
      backends:
        inmemory:
          max_items: 10000
        faiss:
          index_type: "IVF"
          nlist: 100
        hnsw:
          m: 16
          ef_construction: 200
    
    # S7 routing
    router:
      enabled: false  # Default OFF
      mode: inproc  # Options: inproc, service
      service:
        url: "http://router-service:8080"
        timeout_ms: 5000
      cache:
        enabled: true
        s7_permutations: true  # Cache generated permutations
```

#### 1.2 Implement Config Loader

Add to `mef-knowledge/src/config.rs`:

```rust
use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtensionConfig {
    pub knowledge: KnowledgeConfig,
    pub memory: MemoryConfig,
    pub router: RouterConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KnowledgeConfig {
    pub enabled: bool,
    pub inference: InferenceSettings,
    pub derivation: DerivationSettings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InferenceSettings {
    pub threshold: f64,
    pub max_iterations: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DerivationSettings {
    pub root_seed_env: String,
    pub default_path_prefix: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MemoryConfig {
    pub enabled: bool,
    pub backend: String,
    pub backends: BackendConfigs,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackendConfigs {
    pub inmemory: InMemoryConfig,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub faiss: Option<FaissConfig>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub hnsw: Option<HnswConfig>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InMemoryConfig {
    pub max_items: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaissConfig {
    pub index_type: String,
    pub nlist: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HnswConfig {
    pub m: usize,
    pub ef_construction: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RouterConfig {
    pub enabled: bool,
    pub mode: String,
    pub service: ServiceConfig,
    pub cache: CacheConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServiceConfig {
    pub url: String,
    pub timeout_ms: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheConfig {
    pub enabled: bool,
    pub s7_permutations: bool,
}

impl ExtensionConfig {
    pub fn load(path: &str) -> anyhow::Result<Self> {
        let content = fs::read_to_string(path)?;
        let config = serde_yaml::from_str(&content)?;
        Ok(config)
    }
    
    pub fn load_from_env() -> anyhow::Result<Self> {
        let path = std::env::var("MEF_EXTENSION_CONFIG")
            .unwrap_or_else(|_| "config/extension.yaml".to_string());
        Self::load(&path)
    }
}
```

Add `serde_yaml` dependency to `mef-knowledge/Cargo.toml`:

```toml
[dependencies]
serde_yaml = "0.9"
```

### Step 2: Pipeline Integration

#### 2.1 Create Extension Pipeline

Create `mef-knowledge/src/pipeline.rs`:

```rust
use crate::config::ExtensionConfig;
use mef_schemas::{KnowledgeObject, MemoryItem, RouteSpec};
use mef_memory::MemoryStore;
use mef_router::MetatronAdapter;

pub struct ExtensionPipeline {
    config: ExtensionConfig,
    memory_store: Option<MemoryStore>,
    router: Option<MetatronAdapter>,
}

impl ExtensionPipeline {
    pub fn new(config: ExtensionConfig) -> Self {
        let memory_store = if config.memory.enabled {
            Some(MemoryStore::in_memory())
        } else {
            None
        };
        
        let router = if config.router.enabled {
            let mode = match config.router.mode.as_str() {
                "service" => mef_router::AdapterMode::Service,
                _ => mef_router::AdapterMode::InProcess,
            };
            Some(MetatronAdapter::new(mode))
        } else {
            None
        };
        
        Self {
            config,
            memory_store,
            router,
        }
    }
    
    pub fn is_enabled(&self) -> bool {
        self.config.knowledge.enabled
            || self.config.memory.enabled
            || self.config.router.enabled
    }
    
    pub fn process_knowledge(&mut self, knowledge: KnowledgeObject) -> anyhow::Result<()> {
        if !self.config.knowledge.enabled {
            return Ok(());
        }
        
        // Knowledge processing logic (Phase 2 implementation)
        Ok(())
    }
    
    pub fn store_memory(&mut self, item: MemoryItem) -> anyhow::Result<()> {
        if let Some(store) = &mut self.memory_store {
            store.store(item)?;
        }
        Ok(())
    }
    
    pub fn select_route(
        &self,
        seed: &str,
        metrics: &std::collections::HashMap<String, f64>
    ) -> anyhow::Result<Option<RouteSpec>> {
        if let Some(router) = &self.router {
            Ok(Some(router.select_route(seed, metrics)?))
        } else {
            Ok(None)
        }
    }
}
```

#### 2.2 Wire to Core Modules

The extension reads from core modules via public APIs:

```rust
// Example: Reading from mef-core (read-only)
use mef_core::MefCore;

pub struct CoreReader {
    core: Arc<MefCore>,
}

impl CoreReader {
    pub fn new(core: Arc<MefCore>) -> Self {
        Self { core }
    }
    
    // Read-only access to operator state
    pub fn read_operator_state(&self, operator: &str) -> anyhow::Result<OperatorState> {
        self.core.get_operator_state(operator)  // Public API
    }
    
    // Read-only access to spiral coordinates
    pub fn read_spiral_coords(&self, tic_id: &str) -> anyhow::Result<Vec<f64>> {
        self.core.get_spiral_coordinates(tic_id)  // Public API
    }
}
```

**Important**: Never modify core state. All writes go to extension storage.

### Step 3: API Routes (Optional)

#### 3.1 Add Extension API Routes

Add to `mef-api/src/routes/extension.rs`:

```rust
use axum::{
    routing::{get, post},
    Router, Json, Extension,
};
use std::sync::Arc;
use mef_knowledge::ExtensionPipeline;

pub fn extension_routes(pipeline: Arc<ExtensionPipeline>) -> Router {
    Router::new()
        .route("/knowledge/derive", post(derive_knowledge))
        .route("/knowledge/:mef_id", get(get_knowledge))
        .route("/memory/store", post(store_memory))
        .route("/memory/search", post(search_memory))
        .route("/router/select", post(select_route))
        .layer(Extension(pipeline))
}

async fn derive_knowledge(
    Extension(pipeline): Extension<Arc<ExtensionPipeline>>,
    Json(req): Json<DeriveKnowledgeRequest>,
) -> Result<Json<DeriveKnowledgeResponse>, ApiError> {
    // Implementation
}

async fn get_knowledge(
    Extension(pipeline): Extension<Arc<ExtensionPipeline>>,
    Path(mef_id): Path<String>,
) -> Result<Json<KnowledgeObject>, ApiError> {
    // Implementation
}

async fn store_memory(
    Extension(pipeline): Extension<Arc<ExtensionPipeline>>,
    Json(item): Json<MemoryItem>,
) -> Result<Json<StoreResponse>, ApiError> {
    // Implementation
}

async fn search_memory(
    Extension(pipeline): Extension<Arc<ExtensionPipeline>>,
    Json(req): Json<SearchRequest>,
) -> Result<Json<SearchResponse>, ApiError> {
    // Implementation
}

async fn select_route(
    Extension(pipeline): Extension<Arc<ExtensionPipeline>>,
    Json(req): Json<SelectRouteRequest>,
) -> Result<Json<RouteSpec>, ApiError> {
    // Implementation
}
```

#### 3.2 Mount Extension Routes

Add to `mef-api/src/main.rs`:

```rust
use mef_knowledge::{ExtensionConfig, ExtensionPipeline};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Load configuration
    let config = ExtensionConfig::load_from_env()?;
    
    // Create pipeline
    let pipeline = Arc::new(ExtensionPipeline::new(config.clone()));
    
    // Build app
    let app = Router::new()
        .nest("/api/v1", core_routes())
        .nest("/api/v1/extension", extension_routes(pipeline.clone()))
        .layer(/* middleware */);
    
    // Only mount extension routes if enabled
    let app = if pipeline.is_enabled() {
        app
    } else {
        Router::new().nest("/api/v1", core_routes())
    };
    
    // Start server
    let addr = "0.0.0.0:8080".parse()?;
    axum::Server::bind(&addr)
        .serve(app.into_make_service())
        .await?;
    
    Ok(())
}
```

### Step 4: Vector Backends (Optional)

#### 4.1 FAISS Backend

Create `mef-memory/src/faiss.rs`:

```rust
#[cfg(feature = "faiss")]
use faiss::{Index, IndexImpl};
use crate::backend::{MemoryBackend, SearchResult};

#[cfg(feature = "faiss")]
pub struct FaissBackend {
    index: Index,
    items: HashMap<String, MemoryItem>,
}

#[cfg(feature = "faiss")]
impl FaissBackend {
    pub fn new(dimension: usize, config: &FaissConfig) -> anyhow::Result<Self> {
        // Initialize FAISS index
        let index = match config.index_type.as_str() {
            "IVF" => faiss::index_factory(dimension, &format!("IVF{},Flat", config.nlist))?,
            "Flat" => faiss::index_factory(dimension, "Flat")?,
            _ => return Err(anyhow::anyhow!("Unknown FAISS index type")),
        };
        
        Ok(Self {
            index,
            items: HashMap::new(),
        })
    }
}

#[cfg(feature = "faiss")]
impl MemoryBackend for FaissBackend {
    fn store(&mut self, item: MemoryItem) -> crate::Result<()> {
        // Add to FAISS index
        self.index.add(&[item.vector.clone()])?;
        
        // Store item
        self.items.insert(item.id.clone(), item);
        
        Ok(())
    }
    
    fn search(&self, query: &[f64], k: usize) -> crate::Result<Vec<SearchResult>> {
        // Search FAISS index
        let results = self.index.search(&[query.to_vec()], k)?;
        
        // Map results to SearchResult
        let search_results = results.labels[0]
            .iter()
            .zip(results.distances[0].iter())
            .filter_map(|(idx, dist)| {
                self.items.values().nth(*idx as usize).map(|item| SearchResult {
                    item: item.clone(),
                    distance: *dist,
                })
            })
            .collect();
        
        Ok(search_results)
    }
    
    // ... other methods
}
```

#### 4.2 HNSW Backend

Create `mef-memory/src/hnsw.rs`:

```rust
#[cfg(feature = "hnsw")]
use hnsw::{Hnsw, Params};

#[cfg(feature = "hnsw")]
pub struct HnswBackend {
    index: Hnsw<f32, DistanceL2>,
    items: HashMap<String, MemoryItem>,
}

// Similar implementation to FAISS backend
```

### Step 5: Integration Testing

#### 5.1 Create Integration Tests

Create `tests/integration_test.rs`:

```rust
use mef_knowledge::{ExtensionConfig, ExtensionPipeline};
use mef_schemas::{MemoryItem, SpectralSignature};

#[tokio::test]
async fn test_full_pipeline() {
    // Load config
    let config = ExtensionConfig::load("tests/fixtures/test_config.yaml").unwrap();
    
    // Create pipeline
    let mut pipeline = ExtensionPipeline::new(config);
    
    // Test vector construction
    let val = 1.0 / (8.0_f64).sqrt();
    let vector = vec![val; 8];
    let spectral = SpectralSignature {
        psi: 0.3,
        rho: 0.3,
        omega: 0.4,
    };
    
    let item = MemoryItem::new(
        "test_001".to_string(),
        vector,
        spectral,
        None,
    ).unwrap();
    
    // Store in memory
    pipeline.store_memory(item).unwrap();
    
    // Test route selection
    let mut metrics = std::collections::HashMap::new();
    metrics.insert("betti".to_string(), 2.0);
    metrics.insert("lambda_gap".to_string(), 0.5);
    metrics.insert("persistence".to_string(), 0.3);
    
    let route = pipeline.select_route("test_seed", &metrics).unwrap();
    assert!(route.is_some());
}

#[tokio::test]
async fn test_disabled_pipeline() {
    // Create config with all disabled
    let config = ExtensionConfig {
        knowledge: KnowledgeConfig { enabled: false, /* ... */ },
        memory: MemoryConfig { enabled: false, /* ... */ },
        router: RouterConfig { enabled: false, /* ... */ },
    };
    
    let pipeline = ExtensionPipeline::new(config);
    
    // Should not be enabled
    assert!(!pipeline.is_enabled());
}
```

#### 5.2 Run Integration Tests

```bash
cargo test --test integration_test
```

### Step 6: Documentation Updates

#### 6.1 Update README.md

Add extension section to main README:

```markdown
## MEF Knowledge Engine Extension

The MEF system now includes an optional Knowledge Engine extension that adds:

- Knowledge derivation and content addressing
- Vector memory with pluggable backends
- Deterministic S7 route selection
- Gate evaluation logic

See [EXTENSION_README.md](EXTENSION_README.md) for details.

### Enabling the Extension

Edit `config/extension.yaml`:

\```yaml
mef:
  extension:
    knowledge:
      enabled: true
    memory:
      enabled: true
      backend: inmemory
    router:
      enabled: true
      mode: inproc
\```

Restart the MEF service for changes to take effect.
```

#### 6.2 Update API Documentation

Add extension endpoints to OpenAPI spec:

```yaml
/api/v1/extension/knowledge/derive:
  post:
    summary: Derive knowledge object
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              tic_id:
                type: string
              route_id:
                type: string
              seed_path:
                type: string
    responses:
      200:
        description: Knowledge object created
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/KnowledgeObject'
```

### Step 7: Deployment

#### 7.1 Environment Variables

Set required environment variables:

```bash
export MEF_EXTENSION_CONFIG=/path/to/extension.yaml
export MEF_ROOT_SEED=<secure-root-seed>  # From secure vault
```

#### 7.2 Docker Configuration

Update `Dockerfile`:

```dockerfile
FROM rust:1.70 as builder

WORKDIR /app
COPY . .

# Build with extension modules
RUN cargo build --release --workspace

FROM debian:bookworm-slim

COPY --from=builder /app/target/release/mef-api /usr/local/bin/
COPY config/extension.yaml /etc/mef/extension.yaml

ENV MEF_EXTENSION_CONFIG=/etc/mef/extension.yaml

CMD ["mef-api"]
```

#### 7.3 Kubernetes Deployment

Update `deploy/k8s/deployment.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mef-extension-config
data:
  extension.yaml: |
    mef:
      extension:
        knowledge:
          enabled: true
        memory:
          enabled: true
          backend: inmemory
        router:
          enabled: true
          mode: inproc
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mef-api
spec:
  template:
    spec:
      containers:
      - name: mef-api
        image: mef-api:latest
        env:
        - name: MEF_EXTENSION_CONFIG
          value: /etc/mef/extension.yaml
        - name: MEF_ROOT_SEED
          valueFrom:
            secretKeyRef:
              name: mef-secrets
              key: root-seed
        volumeMounts:
        - name: config
          mountPath: /etc/mef
      volumes:
      - name: config
        configMap:
          name: mef-extension-config
```

### Step 8: Monitoring & Observability

#### 8.1 Add Metrics

Add Prometheus metrics:

```rust
use prometheus::{register_counter, register_histogram, Counter, Histogram};

lazy_static! {
    static ref KNOWLEDGE_DERIVED: Counter = register_counter!(
        "mef_knowledge_derived_total",
        "Total number of knowledge objects derived"
    ).unwrap();
    
    static ref MEMORY_SEARCH_DURATION: Histogram = register_histogram!(
        "mef_memory_search_duration_seconds",
        "Memory search duration"
    ).unwrap();
    
    static ref ROUTE_SELECTION_DURATION: Histogram = register_histogram!(
        "mef_route_selection_duration_seconds",
        "Route selection duration"
    ).unwrap();
}

// Use in pipeline
KNOWLEDGE_DERIVED.inc();
let timer = MEMORY_SEARCH_DURATION.start_timer();
// ... search operation
timer.observe_duration();
```

#### 8.2 Add Tracing

Add structured logging:

```rust
use tracing::{info, warn, error, instrument};

#[instrument(skip(self))]
pub fn process_knowledge(&mut self, knowledge: KnowledgeObject) -> anyhow::Result<()> {
    info!("Processing knowledge object: {}", knowledge.mef_id);
    
    // ... processing logic
    
    info!("Knowledge processed successfully");
    Ok(())
}
```

### Step 9: Performance Optimization

#### 9.1 Cache S7 Permutations

```rust
use once_cell::sync::Lazy;

static S7_PERMUTATIONS: Lazy<Vec<Vec<usize>>> = Lazy::new(|| {
    generate_s7_permutations()
});

pub fn select_route_cached(seed: &str, metrics: &HashMap<String, f64>) -> Result<RouteSpec> {
    let s7 = &*S7_PERMUTATIONS;  // Use cached permutations
    // ... selection logic
}
```

#### 9.2 Batch Operations

```rust
impl MemoryStore {
    pub fn store_batch(&mut self, items: Vec<MemoryItem>) -> Result<()> {
        for item in items {
            self.store(item)?;
        }
        Ok(())
    }
}
```

### Step 10: Rollback Plan

If issues arise, disable extension via config:

```yaml
mef:
  extension:
    knowledge:
      enabled: false  # Disable extension
    memory:
      enabled: false
    router:
      enabled: false
```

Restart service:

```bash
kubectl rollout restart deployment/mef-api
```

System will revert to pre-extension behavior with zero overhead.

## Verification Checklist

- [ ] Configuration loads successfully
- [ ] Pipeline initializes with config
- [ ] Extension API routes respond
- [ ] Core functionality unchanged
- [ ] Tests pass (unit + integration)
- [ ] Metrics reporting correctly
- [ ] Logs structured and readable
- [ ] Rollback tested and works
- [ ] Documentation updated
- [ ] Performance benchmarks run

## Success Criteria

- ✅ Extension can be enabled/disabled via config
- ✅ Zero impact on core when disabled
- ✅ All tests passing (unit + integration)
- ✅ API endpoints functional
- ✅ Metrics and logging working
- ✅ Performance within acceptable limits
- ✅ Rollback plan tested

## Next Steps

- Implement FAISS backend for large-scale vector search
- Add HNSW backend for low-latency queries
- Implement distributed routing service
- Add advanced knowledge inference
- Scale testing with production data

## Support

For integration issues:
1. Check configuration validity
2. Verify environment variables set
3. Review logs for errors
4. Check metrics for anomalies
5. Consult troubleshooting guide
6. Open GitHub issue with details
