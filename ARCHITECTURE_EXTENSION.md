# MEF Knowledge Engine - Extension Architecture

**Document Version:** 1.0.0  
**Blueprint:** SPEC-006 (Infinity-Ledger_Expansion_1-4.pdf)  
**Date:** October 2025  
**Status:** Scaffold Implementation (Phase 1)

## Table of Contents

1. [Overview](#overview)
2. [Design Principles](#design-principles)
3. [Module Structure](#module-structure)
4. [Integration Points](#integration-points)
5. [Configuration System](#configuration-system)
6. [Mathematical Foundations](#mathematical-foundations)
7. [Extension Points](#extension-points)
8. [Implementation Status](#implementation-status)
9. [Next Steps](#next-steps)

---

## Overview

This document describes the architecture of the MEF Knowledge Engine extension, a Rust-based implementation of SPEC-006 that extends the existing MEF-Core system without modifying its internals.

### Key Characteristics

- **ADD-ONLY**: No modifications to core system
- **Feature-Gated**: All functionality disabled by default
- **Modular**: Clean separation of concerns
- **Deterministic**: Reproducible results from same inputs
- **Extensible**: Designed for future development

### Extension Modules

The extension consists of four new workspace members:

```
mef-schemas/     - Schema definitions and type system
mef-knowledge/   - Knowledge derivation and inference
mef-memory/      - Vector memory indexing
mef-router/      - Metatron S7 route selection
```

---

## Design Principles

### 1. Non-Destructive Integration

**MUST NOT:**
- Modify core operators (DK, SW, PI, WT)
- Change Solve-Coagula iteration logic
- Alter PoR decision thresholds
- Modify existing JSON schemas
- Remove or rename public endpoints
- Log or persist root seeds (BIP-39 mnemonic)

**MAY:**
- Add new modules under separate namespace
- Create compatibility shims for imports
- Add new config keys with safe defaults
- Include new API routes under new prefixes

### 2. Feature Flags & Safe Defaults

All extension functionality is controlled by feature flags:

```yaml
knowledge:
  enabled: false  # Default OFF

memory:
  enabled: false  # Default OFF
  
router:
  mode: inproc    # Default in-process
```

**Behavior Guarantee:** With all flags set to `false`, the system behaves identically to pre-extension state.

### 3. Determinism

All operations must be deterministic:

- Same inputs + same seed → same outputs
- Canonical JSON with stable key ordering
- Fixed float precision (6 decimals)
- No time-based seeds or random values in critical paths
- Content addressing via HASH(canonical(TIC) || route_id || seed_path)

### 4. Adapter Pattern

Integration with core modules uses adapters instead of direct modification:

```rust
// ✓ CORRECT: Use adapter
let adapter = MetatronAdapter::default();
let route = adapter.get_route(seed, context).await?;

// ✗ WRONG: Direct modification of core
// Modify mef-topology/src/metatron.rs  <-- FORBIDDEN
```

---

## Module Structure

### mef-schemas

**Purpose:** JSON schema definitions and Rust type system for extension

**Components:**

```rust
pub mod route_spec;      // RouteSpec, OperatorSlot
pub mod memory_item;     // MemoryItem, SpectralSignature, PorStatus
pub mod knowledge;       // KnowledgeObject, TicReference, RouteReference
pub mod gate;            // MerkabaGateEvent, GateChecks, GateDecision
```

**Key Types:**

- `RouteSpec`: 7-slot S7 permutation for Solve-Coagula
- `MemoryItem`: 8D normalized vector with metadata
- `KnowledgeObject`: TIC + route + seed_path binding
- `MerkabaGateEvent`: Gate decision (FIRE/HOLD)

**No Dependencies on Core:** This module is independent and can be used by other systems.

### mef-knowledge

**Purpose:** Knowledge derivation, projection, and validation

**Components:**

```rust
pub mod primitives;      // Canonical JSON, content hash, seed derivation
pub mod metric;          // Vector8Builder (5D + 3D → 8D)
pub mod inference;       // ProjectionMode, validation
pub mod derivation;      // End-to-end knowledge derivation pipeline
```

**Key Functions:**

- `canonical_json()`: Deterministic serialization
- `compute_mef_id()`: Content-addressed knowledge ID
- `derive_seed()`: HD-style seed derivation (HMAC-SHA256)
- `Vector8Builder::build()`: Construct normalized 8D vectors
- `KnowledgeDerivation::derive()`: Full pipeline orchestration

**Dependencies:** mef-spiral, mef-ledger, mef-hdag (read-only)

### mef-memory

**Purpose:** Vector database abstraction and similarity search

**Components:**

```rust
pub mod index;           // MemoryIndex, MemoryConfig
pub mod operations;      // UpsertRequest, SearchRequest, SearchResult
pub mod backends;        // VectorBackend trait, InMemoryBackend
```

**Key Features:**

- **No-op when disabled**: All operations return immediately
- **Pluggable backends**: In-memory, FAISS, HNSW (future)
- **8D vectors only**: Enforced at type level
- **Cosine similarity**: L2 distance on normalized vectors

**Backend Trait:**

```rust
#[async_trait]
pub trait VectorBackend: Send + Sync {
    async fn upsert(&mut self, item: MemoryItem) -> Result<(), String>;
    async fn search(&self, query: &[f64], top_k: usize, ...) -> Result<Vec<(String, f64)>, String>;
    async fn get(&self, id: &str) -> Result<Option<MemoryItem>, String>;
    // ...
}
```

**Dependencies:** mef-schemas, mef-knowledge

### mef-router

**Purpose:** Metatron S7 route selection without core modification

**Components:**

```rust
pub mod s7;              // generate_permutations(), select_route()
pub mod scoring;         // mesh_score(), extract_mesh_metrics()
pub mod adapter;         // MetatronAdapter (inproc/service modes)
```

**Key Algorithm:**

```
1. Generate S7: all 7! = 5040 permutations of [1,2,3,4,5,6,7]
2. Compute J(m) = 0.10*betti + 0.70*lambda_gap + 0.20*persistence
3. Hash seed + metrics → deterministic index
4. Select permutation: (hash + k) mod 5040, where k = |J(m)|*1000 mod 5040
5. Map to operators: [DK, SW, PI, WT, RES1, ADAPTER, RES2]
```

**Dependencies:** mef-topology (read-only via adapter), mef-solvecoagula (provides route)

---

## Integration Points

### Reading from Core Modules

The extension reads from (but never modifies) these core modules:

| Core Module | What We Read | How We Read |
|-------------|-------------|-------------|
| `mef-spiral` | 5D coordinates, spectral signature | Via public API |
| `mef-ledger` | TIC blocks, chain state | Via public API |
| `mef-hdag` | Graph structure, node relationships | Via public API |
| `mef-topology` | Mesh metrics (Betti, λ-gap) | Via `MetatronAdapter` |
| `mef-audit` | Gate decisions | Via public API |
| `mef-tic` | TIC invariants | Via public API |

### Providing to Core Modules

The extension provides these services back to core:

| To Module | What We Provide | How |
|-----------|----------------|-----|
| `mef-solvecoagula` | Route specification | Via config or adapter |
| `mef-ledger` | Proof bundles (extended) | Via new fields |
| `mef-hdag` | Knowledge relationships | Via new edges |

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    MEF-Core System                          │
│  ┌─────────┐   ┌────────┐   ┌──────┐   ┌───────┐          │
│  │ Spiral  │──▶│  PoR   │──▶│ Solve│──▶│ Gate  │          │
│  │  (5D)   │   │ Valid? │   │Coagula   │ FIRE? │          │
│  └─────────┘   └────────┘   └──────┘   └───────┘          │
│       │            │            │            │              │
└───────┼────────────┼────────────┼────────────┼──────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌──────────────────────────────────────────────────────────────┐
│                Extension Layer (ADD-ONLY)                     │
│                                                               │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐     │
│  │ mef-router   │   │ mef-knowledge│   │ mef-memory  │     │
│  │ S7 selection │   │ 8D vectors   │   │ Index       │     │
│  └──────────────┘   └──────────────┘   └─────────────┘     │
│         │                  │                   │             │
│         └──────────────────┴───────────────────┘             │
│                            │                                 │
│                    ┌───────▼────────┐                        │
│                    │ KnowledgeObject│                        │
│                    │   (mef_id)     │                        │
│                    └────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

---

## Configuration System

### Structure

```yaml
# config.yaml (ADD-ONLY, no core changes)

knowledge:
  enabled: false              # Master switch
  
memory:
  enabled: false              # Master switch
  path: ""                    # Index storage path (empty = disabled)
  dimension: 8                # Fixed for MEF
  metric: cosine              # Distance metric
  backend: in-memory          # Backend type
  
router:
  mode: inproc                # inproc | service
  service_url: null           # Required if mode=service
  
paths:
  memory: ""                  # Memory index path
  
# Safe defaults ensure zero impact when disabled
```

### Loading Configuration

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ExtensionConfig {
    pub knowledge: KnowledgeConfig,
    pub memory: MemoryConfig,
    pub router: RouterConfig,
    pub paths: PathsConfig,
}

impl Default for ExtensionConfig {
    fn default() -> Self {
        Self {
            knowledge: KnowledgeConfig { enabled: false },
            memory: MemoryConfig {
                enabled: false,
                path: None,
                dimension: 8,
                metric: "cosine".to_string(),
                backend: "in-memory".to_string(),
            },
            router: RouterConfig {
                mode: RouterMode::InProc,
                service_url: None,
            },
            paths: PathsConfig {
                memory: None,
            },
        }
    }
}
```

---

## Mathematical Foundations

### Spiral Embedding (5D → 8D)

**Input:** 5D coordinates x = (x₁, x₂, x₃, x₄, x₅) from spiral  
**Spectral:** σ = (ψ, ρ, ω) from PoR  
**Weights:** w = (w₁..w₅, wψ, wρ, wω)

**Construction:**

```
z' = [w₁·x₁, w₂·x₂, w₃·x₃, w₄·x₄, w₅·x₅, wψ·ψ, wρ·ρ, wω·ω]
ẑ = z' / ||z'||₂
```

**Properties:**
- Normalized: ||ẑ||₂ = 1
- Deterministic: Same input → same output
- Cosine = L2: cos(ẑ,ŷ) = 1 - ||ẑ-ŷ||²/2

### Route Selection (S7)

**Permutation Space:** 7! = 5040 routes

**Mesh Score:**

```
J(m) = 0.10·betti + 0.70·λ_gap + 0.20·persistence
```

**Selection:**

```
perms = all_permutations([1,2,3,4,5,6,7])
hash = SHA256(seed || metrics)
k = (|J(m)| · 1000) mod 5040
idx = (hash + k) mod 5040
route = perms[idx]
```

**Determinism:** Same seed + same metrics → same route

### Gate Conditions (FIRE/HOLD)

**FIRE ⟺ All conditions satisfied:**

```
PoR = valid
ΔPI ≤ ε_pi      (path invariance)
Φ ≥ φ_threshold  (alignment)
ΔV < 0          (Lyapunov decrease)
```

**Default Thresholds:**
- ε_pi = 0.01
- φ_threshold = 0.85

---

## Extension Points

### 1. Vector Database Backends

**Current:** In-memory only  
**Future:** Implement `VectorBackend` trait for:
- FAISS (Facebook AI Similarity Search)
- HNSW (Hierarchical Navigable Small World)
- Qdrant, Milvus, Pinecone, etc.

**How to Add:**

```rust
pub struct FaissBackend {
    index: faiss::Index,
}

#[async_trait]
impl VectorBackend for FaissBackend {
    async fn upsert(&mut self, item: MemoryItem) -> Result<(), String> {
        // TODO: Implement FAISS upsert
    }
    // ... implement other methods
}
```

### 2. Router Service Mode

**Current:** In-process adapter only  
**Future:** Implement HTTP client for external Metatron service

**How to Add:**

```rust
// In mef-router/src/adapter.rs
impl MetatronAdapter {
    async fn get_route_service(&self, seed: &str) -> Result<RouteSpec, AdapterError> {
        let client = reqwest::Client::new();
        let response = client
            .post(self.service_url.as_ref().unwrap())
            .json(&json!({"seed": seed}))
            .send()
            .await?;
        // Parse RouteSpec from response
    }
}
```

### 3. API Routes

**Not Included in Scaffold** (optional future work)

**How to Add:**

```rust
// Create mef-api-extensions/ or add to existing mef-api/

use axum::{Router, routing::{get, post}};
use mef_knowledge::KnowledgeDerivation;
use mef_memory::MemoryIndex;

pub fn knowledge_routes() -> Router {
    Router::new()
        .route("/knowledge/derive", post(derive_handler))
        .route("/knowledge/validate", post(validate_handler))
}

pub fn memory_routes() -> Router {
    Router::new()
        .route("/memory/upsert", post(upsert_handler))
        .route("/memory/search", post(search_handler))
}

pub fn router_routes() -> Router {
    Router::new()
        .route("/router/select", post(select_route_handler))
}
```

### 4. Full Derivation Pipeline

**Current:** Placeholder implementation  
**Future:** Wire up complete pipeline

**TODO in `mef-knowledge/src/derivation.rs`:**

```rust
pub async fn derive(&self, request: DeriveRequest) -> Result<DeriveResponse, DerivationError> {
    // Step 1: Normalize via acquisition
    let normalized = mef_ingestion::normalize(request.payload)?;
    
    // Step 2: Generate spiral snapshot
    let snapshot = mef_spiral::snapshot(normalized, seed)?;
    
    // Step 3: Compute PoR
    let por = mef_spiral::compute_por(&snapshot)?;
    if por.status != "valid" {
        return Err(DerivationError::PorFailed("PoR invalid".to_string()));
    }
    
    // Step 4: Select route
    let adapter = MetatronAdapter::default();
    let route = adapter.get_route(&request.seed_path, None).await?;
    
    // Step 5: Execute Solve-Coagula
    let result = mef_solvecoagula::iterate(&snapshot, &route)?;
    
    // Step 6: Evaluate gate
    let gate_event = mef_audit::evaluate_gate(&result)?;
    if !gate_event.is_fire() {
        return Err(DerivationError::GateHeld(gate_event.decision.reason));
    }
    
    // Step 7: Crystallize TIC
    let tic = mef_tic::crystallize(&result)?;
    
    // Step 8: Bind knowledge
    let mef_id = compute_mef_id(&tic, &route.route_id, &request.seed_path)?;
    let knowledge = KnowledgeObject::new(mef_id, tic, route, request.seed_path, 0);
    
    // Step 9: Append to ledger
    let block = mef_ledger::append_block(knowledge.clone())?;
    
    Ok(DeriveResponse { knowledge, tic_id: tic.tic_id, proof: gate_event, block })
}
```

---

## Implementation Status

### ✅ Completed (Phase 1: Scaffold)

- [x] mef-schemas module with all schema types
- [x] mef-knowledge module with primitives and metrics
- [x] mef-memory module with index abstraction
- [x] mef-router module with S7 algorithm
- [x] 51 passing unit tests
- [x] Clean build with zero core modifications
- [x] Feature flags architecture
- [x] Deterministic primitives (canonical JSON, hashing, seed derivation)

### 🔄 In Progress (Phase 2: Integration)

- [ ] Configuration system implementation
- [ ] API route handlers
- [ ] Full derivation pipeline wiring
- [ ] Backend integrations (FAISS, HNSW)
- [ ] Service mode for router

### 📋 Future Work (Phase 3+)

- [ ] Performance optimization
- [ ] Caching layers
- [ ] Distributed deployment support
- [ ] Advanced analytics
- [ ] CLI commands
- [ ] Monitoring and observability

---

## Next Steps

### For Agent Iteration 2

1. **Wire Up Derivation Pipeline**
   - Implement actual calls to core modules in `derivation.rs`
   - Add error handling and retry logic
   - Test end-to-end flow

2. **Add Configuration Loading**
   - Create config file parser
   - Add validation
   - Integrate with existing config system

3. **Implement API Routes** (optional)
   - Add endpoints to `mef-api`
   - Use feature flags to gate functionality
   - Add OpenAPI documentation

### For Agent Iteration 3

1. **Add Vector Database Backends**
   - Implement FAISS backend
   - Implement HNSW backend
   - Add benchmark comparisons

2. **Service Mode for Router**
   - HTTP client implementation
   - Retry and fallback logic
   - Service discovery

3. **Performance Optimization**
   - Profile critical paths
   - Add caching
   - Optimize S7 generation

---

## Testing Strategy

### Unit Tests

Each module has comprehensive unit tests:

```bash
cargo test --package mef-schemas   # 9 tests
cargo test --package mef-knowledge # 20 tests
cargo test --package mef-router    # 15 tests
cargo test --package mef-memory    # 7 tests
```

### Integration Tests

TODO: Add integration tests that verify:
- End-to-end derivation flow
- Core system unaffected when features disabled
- Determinism across runs

### Property Tests

TODO: Add property-based tests using `proptest`:
- Route selection is deterministic
- Vector normalization preserves properties
- Canonical JSON is stable

---

## Security Considerations

### BIP-39 Seed Management

**CRITICAL:** Root seeds MUST NEVER be logged or persisted.

```rust
// ✓ CORRECT: Only derive and use
let derived = derive_seed(&root_seed, "MEF/domain/stage/0001");
// Use derived seed...
// root_seed is dropped after use

// ✗ WRONG: Logging or persisting root seed
tracing::info!("Root seed: {:?}", root_seed);  // FORBIDDEN
store_in_db(root_seed);                         // FORBIDDEN
```

### Content Addressing

All knowledge objects are content-addressed:

```
mef_id = HASH(canonical(TIC) || route_id || seed_path)[:32]
```

This ensures:
- Immutability (changing content changes ID)
- Verifiability (recompute to verify)
- Uniqueness (hash collisions negligible)

---

## References

### Documentation

- [SPEC-006](./Infinity-Ledger_Expansion_1-4.pdf): Original blueprint
- [EXTENSION_INTEGRATION.md](./EXTENSION_INTEGRATION.md): Integration guide
- [MEF-Core README](./README.md): Core system documentation

### Code Locations

```
mef-schemas/
├── src/
│   ├── lib.rs           # Module exports
│   ├── route_spec.rs    # RouteSpec, OperatorSlot
│   ├── memory_item.rs   # MemoryItem, SpectralSignature
│   ├── knowledge.rs     # KnowledgeObject
│   └── gate.rs          # MerkabaGateEvent

mef-knowledge/
├── src/
│   ├── lib.rs           # Module exports
│   ├── primitives.rs    # Canonical JSON, hashing
│   ├── metric.rs        # Vector8Builder
│   ├── inference.rs     # Projection, validation
│   └── derivation.rs    # Pipeline orchestration

mef-memory/
├── src/
│   ├── lib.rs           # Module exports
│   ├── index.rs         # MemoryIndex
│   ├── operations.rs    # Request/response types
│   └── backends.rs      # VectorBackend trait

mef-router/
├── src/
│   ├── lib.rs           # Module exports
│   ├── s7.rs            # Permutation generation
│   ├── scoring.rs       # Mesh metric computation
│   └── adapter.rs       # MetatronAdapter
```

---

## Appendix: Design Decisions

### Why Rust?

1. **Type Safety**: Compile-time guarantees prevent many runtime errors
2. **Performance**: Zero-cost abstractions, no GC pauses
3. **Memory Safety**: No null pointers, no data races
4. **Ecosystem**: Excellent async support (Tokio), serialization (Serde), etc.

### Why ADD-ONLY?

1. **Safety**: No risk of breaking existing functionality
2. **Reversibility**: Can disable entire extension via flags
3. **Testing**: Core tests remain valid
4. **Migration**: Gradual adoption possible

### Why Feature Flags?

1. **Zero Overhead**: When disabled, no runtime cost
2. **Experimentation**: Easy to test new features
3. **Deployment**: Progressive rollout
4. **Backwards Compatibility**: Old configs still work

---

**Document Maintained By:** MEF-Core Extension Team  
**Last Updated:** October 2025  
**Version:** 1.0.0
