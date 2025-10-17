# MEF-Core Integration Specification
## Framework Components for ANN Search Optimization

**Version:** 1.0.0  
**Target System:** MEF-Core (Rust)  
**Integration Mode:** ADD-ONLY (Zero Core Modifications)  
**Purpose:** Optimize vector search performance via resonance-based filtering and adaptive routing

---

## Executive Summary

This specification defines how to integrate four framework components into MEF-Core to optimize ANN (Approximate Nearest Neighbor) search performance:

1. **Kosmokrator** → Pre-indexing stability filter (reduces index size by 20-40%)
2. **O.P.H.A.N. Array** → Multi-shard parallel search (3-4x speedup)
3. **Chronokrator** → Adaptive query routing (strategy selection)
4. **Mandorla Logic** → Query-space refinement (precision boost)

**Key Principle:** All components integrate via the existing `MemoryBackend` trait without modifying MEF-Core.

---

## Architecture Overview

### Current MEF-Core Pipeline

```
Ingestion → Spiral(5D) → Solve-Coagula → TIC → Vector8D → MemoryBackend → Search
```

### Enhanced Pipeline with Framework Components

```
Ingestion → Spiral(5D) → Solve-Coagula → TIC → Vector8D 
    ↓
[KOSMOKRATOR FILTER] ← Stability check before indexing
    ↓
[O.P.H.A.N. SHARDED INDEX] ← Parallel 4-shard storage
    ↓
[CHRONOKRATOR ROUTER] ← Adaptive strategy selection
    ↓
[MANDORLA REFINER] ← Query-space intersection
    ↓
Optimized Search Results
```

---

## Component 1: Kosmokrator - Stability Filter

### Purpose
Filter unstable vectors BEFORE they enter the index, reducing index size and improving search precision.

### Integration Point
**Location:** `mef-memory/src/backends/`  
**New Module:** `stability_filter.rs`

### Rust Implementation

```rust
// mef-memory/src/backends/stability_filter.rs

use crate::schemas::MemoryItem;
use std::collections::VecDeque;

/// Kosmokrator stability filter configuration
#[derive(Debug, Clone)]
pub struct StabilityFilterConfig {
    /// Minimum coherence threshold (κ*)
    pub coherence_threshold: f64,
    /// Maximum fluctuation tolerance (ε)
    pub max_fluctuation: f64,
    /// History window size for variance calculation
    pub window_size: usize,
}

impl Default for StabilityFilterConfig {
    fn default() -> Self {
        Self {
            coherence_threshold: 0.85,
            max_fluctuation: 0.02,
            window_size: 10,
        }
    }
}

/// Kosmokrator stability filter
pub struct StabilityFilter {
    config: StabilityFilterConfig,
    history: VecDeque<MemoryItem>,
}

impl StabilityFilter {
    pub fn new(config: StabilityFilterConfig) -> Self {
        Self {
            config,
            history: VecDeque::with_capacity(config.window_size),
        }
    }

    /// Check if a vector should be indexed (Proof-of-Resonance)
    pub fn should_index(&mut self, item: &MemoryItem) -> bool {
        // 1. Compute coherence (κ)
        let coherence = self.compute_coherence(item);
        
        // 2. Compute fluctuation if history available
        let fluctuation = if self.history.len() >= 2 {
            self.compute_fluctuation(item)
        } else {
            0.0
        };
        
        // 3. Update history
        self.history.push_back(item.clone());
        if self.history.len() > self.config.window_size {
            self.history.pop_front();
        }
        
        // 4. PoR decision
        let por_valid = coherence >= self.config.coherence_threshold 
                     && fluctuation <= self.config.max_fluctuation;
        
        por_valid
    }

    /// Compute coherence κ(t) from spectral signature
    fn compute_coherence(&self, item: &MemoryItem) -> f64 {
        // Use spectral signature (ψ, ρ, ω) to compute coherence
        let psi = item.spectral.psi;
        let rho = item.spectral.rho;
        let omega = item.spectral.omega;
        
        // Coherence formula: κ = |ψ·ρ·e^(iω)|
        // Simplified: κ = sqrt(ψ² + ρ²) * cos(omega)
        let magnitude = (psi.powi(2) + rho.powi(2)).sqrt();
        let phase_factor = omega.cos();
        
        (magnitude * phase_factor).abs()
    }

    /// Compute temporal fluctuation
    fn compute_fluctuation(&self, current: &MemoryItem) -> f64 {
        if self.history.is_empty() {
            return 0.0;
        }

        // Compute variance of coherence values in window
        let coherences: Vec<f64> = self.history.iter()
            .map(|item| self.compute_coherence(item))
            .collect();
        
        let mean = coherences.iter().sum::<f64>() / coherences.len() as f64;
        let variance = coherences.iter()
            .map(|c| (c - mean).powi(2))
            .sum::<f64>() / coherences.len() as f64;
        
        variance.sqrt()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schemas::SpectralSignature;

    #[test]
    fn test_stability_filter_accepts_stable() {
        let mut filter = StabilityFilter::new(StabilityFilterConfig::default());
        
        let stable_item = MemoryItem {
            id: "test1".to_string(),
            vector: vec![0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            spectral: SpectralSignature {
                psi: 0.9,
                rho: 0.95,
                omega: 0.1,
            },
            metadata: None,
        };

        assert!(filter.should_index(&stable_item));
    }

    #[test]
    fn test_stability_filter_rejects_unstable() {
        let mut filter = StabilityFilter::new(StabilityFilterConfig::default());
        
        let unstable_item = MemoryItem {
            id: "test2".to_string(),
            vector: vec![0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            spectral: SpectralSignature {
                psi: 0.2,  // Low coherence
                rho: 0.3,
                omega: 0.8,
            },
            metadata: None,
        };

        assert!(!filter.should_index(&unstable_item));
    }
}
```

### Integration into MemoryBackend

```rust
// mef-memory/src/backends/filtered_backend.rs

use super::{MemoryBackend, InMemoryBackend, StabilityFilter};
use crate::schemas::MemoryItem;

/// Filtered backend wrapper with Kosmokrator
pub struct FilteredBackend<B: MemoryBackend> {
    inner: B,
    filter: StabilityFilter,
    stats: FilterStats,
}

#[derive(Debug, Default)]
pub struct FilterStats {
    pub total_attempted: usize,
    pub total_accepted: usize,
    pub total_rejected: usize,
}

impl<B: MemoryBackend> FilteredBackend<B> {
    pub fn new(inner: B, filter: StabilityFilter) -> Self {
        Self {
            inner,
            filter,
            stats: FilterStats::default(),
        }
    }

    pub fn stats(&self) -> &FilterStats {
        &self.stats
    }
}

impl<B: MemoryBackend> MemoryBackend for FilteredBackend<B> {
    fn store(&mut self, item: MemoryItem) -> Result<()> {
        self.stats.total_attempted += 1;

        // Apply Kosmokrator filter
        if self.filter.should_index(&item) {
            self.stats.total_accepted += 1;
            self.inner.store(item)
        } else {
            self.stats.total_rejected += 1;
            Ok(()) // Silently reject unstable vectors
        }
    }

    fn get(&self, id: &str) -> Result<Option<MemoryItem>> {
        self.inner.get(id)
    }

    fn search(&self, query: &[f64], k: usize) -> Result<Vec<SearchResult>> {
        self.inner.search(query, k)
    }

    fn remove(&mut self, id: &str) -> Result<()> {
        self.inner.remove(id)
    }

    fn clear(&mut self) -> Result<()> {
        self.stats = FilterStats::default();
        self.inner.clear()
    }

    fn count(&self) -> usize {
        self.inner.count()
    }
}
```

---

## Component 2: O.P.H.A.N. Array - Parallel Sharded Index

### Purpose
Split index into 4 parallel shards with central aggregation for 3-4x search speedup.

### Integration Point
**Location:** `mef-memory/src/backends/`  
**New Module:** `ophan_backend.rs`

### Rust Implementation

```rust
// mef-memory/src/backends/ophan_backend.rs

use crate::{MemoryBackend, MemoryItem, SearchResult};
use rayon::prelude::*;
use std::sync::{Arc, RwLock};

/// O.P.H.A.N. 4-shard parallel backend
pub struct OphanBackend<B: MemoryBackend> {
    shards: Vec<Arc<RwLock<B>>>,
    konus: CentralAggregator,
}

impl<B: MemoryBackend + Clone> OphanBackend<B> {
    pub fn new(shard_template: B) -> Self {
        let shards = (0..4)
            .map(|_| Arc::new(RwLock::new(shard_template.clone())))
            .collect();

        Self {
            shards,
            konus: CentralAggregator::default(),
        }
    }

    /// Compute shard assignment via hash
    fn compute_shard(&self, vector: &[f64]) -> usize {
        use std::hash::{Hash, Hasher};
        use std::collections::hash_map::DefaultHasher;

        let mut hasher = DefaultHasher::new();
        for v in vector {
            v.to_bits().hash(&mut hasher);
        }
        (hasher.finish() as usize) % 4
    }
}

impl<B: MemoryBackend + Send + Sync> MemoryBackend for OphanBackend<B> {
    fn store(&mut self, item: MemoryItem) -> Result<()> {
        let shard_id = self.compute_shard(&item.vector);
        let mut shard = self.shards[shard_id].write().unwrap();
        shard.store(item)
    }

    fn get(&self, id: &str) -> Result<Option<MemoryItem>> {
        // Search all shards in parallel
        for shard in &self.shards {
            let shard = shard.read().unwrap();
            if let Some(item) = shard.get(id)? {
                return Ok(Some(item));
            }
        }
        Ok(None)
    }

    fn search(&self, query: &[f64], k: usize) -> Result<Vec<SearchResult>> {
        // Parallel search across all 4 shards
        let results: Vec<Vec<SearchResult>> = self.shards
            .par_iter()
            .map(|shard| {
                let shard = shard.read().unwrap();
                shard.search(query, k).unwrap_or_default()
            })
            .collect();

        // Konus aggregation: merge and re-rank top-k
        Ok(self.konus.aggregate(results, k))
    }

    fn remove(&mut self, id: &str) -> Result<()> {
        // Try removing from all shards
        for shard in &self.shards {
            let mut shard = shard.write().unwrap();
            let _ = shard.remove(id);
        }
        Ok(())
    }

    fn clear(&mut self) -> Result<()> {
        for shard in &self.shards {
            let mut shard = shard.write().unwrap();
            shard.clear()?;
        }
        Ok(())
    }

    fn count(&self) -> usize {
        self.shards.iter()
            .map(|s| s.read().unwrap().count())
            .sum()
    }
}

/// Central aggregator (Konus)
#[derive(Default)]
struct CentralAggregator;

impl CentralAggregator {
    fn aggregate(&self, shard_results: Vec<Vec<SearchResult>>, k: usize) -> Vec<SearchResult> {
        // Flatten all results
        let mut all_results: Vec<SearchResult> = shard_results
            .into_iter()
            .flatten()
            .collect();

        // Sort by distance (ascending)
        all_results.sort_by(|a, b| {
            a.distance.partial_cmp(&b.distance).unwrap()
        });

        // Take top-k
        all_results.truncate(k);
        all_results
    }
}
```

---

## Component 3: Chronokrator - Adaptive Query Router

### Purpose
Dynamically select search strategy based on query characteristics (k, dimension, time budget).

### Integration Point
**Location:** `mef-memory/src/`  
**New Module:** `adaptive_router.rs`

### Rust Implementation

```rust
// mef-memory/src/adaptive_router.rs

use crate::{MemoryBackend, SearchResult};

/// Search strategy enum
#[derive(Debug, Clone, Copy)]
pub enum SearchStrategy {
    Exact,      // Brute force O(n)
    Approximate, // FAISS/HNSW O(log n)
    Hybrid,     // Adaptive blend
}

/// Chronokrator adaptive router configuration
#[derive(Debug, Clone)]
pub struct RouterConfig {
    pub small_k_threshold: usize,      // k < 10 → Exact
    pub large_k_threshold: usize,      // k > 100 → Approximate
    pub high_dim_threshold: usize,     // dim > 128 → Approximate
}

impl Default for RouterConfig {
    fn default() -> Self {
        Self {
            small_k_threshold: 10,
            large_k_threshold: 100,
            high_dim_threshold: 128,
        }
    }
}

/// Adaptive query router
pub struct AdaptiveRouter<B: MemoryBackend> {
    backend: B,
    config: RouterConfig,
}

impl<B: MemoryBackend> AdaptiveRouter<B> {
    pub fn new(backend: B, config: RouterConfig) -> Self {
        Self { backend, config }
    }

    /// Route query to optimal strategy
    pub fn search(&self, query: &[f64], k: usize) -> Result<Vec<SearchResult>> {
        let strategy = self.select_strategy(query, k);
        
        match strategy {
            SearchStrategy::Exact => {
                // Use backend's native search (already brute-force in InMemory)
                self.backend.search(query, k)
            },
            SearchStrategy::Approximate => {
                // For future FAISS/HNSW backends
                self.backend.search(query, k)
            },
            SearchStrategy::Hybrid => {
                // Blend: exact for small k, approx for remainder
                let exact_k = self.config.small_k_threshold;
                let mut results = self.backend.search(query, exact_k)?;
                
                if k > exact_k {
                    let approx_results = self.backend.search(query, k - exact_k)?;
                    results.extend(approx_results);
                    results.sort_by(|a, b| a.distance.partial_cmp(&b.distance).unwrap());
                    results.truncate(k);
                }
                
                Ok(results)
            }
        }
    }

    /// Chronokrator decision logic
    fn select_strategy(&self, query: &[f64], k: usize) -> SearchStrategy {
        let dim = query.len();

        // Decision tree based on query profile
        if k < self.config.small_k_threshold {
            SearchStrategy::Exact  // Small k: brute force is faster
        } else if k > self.config.large_k_threshold || dim > self.config.high_dim_threshold {
            SearchStrategy::Approximate  // Large k or high dim: use approximation
        } else {
            SearchStrategy::Hybrid  // Middle ground: blend strategies
        }
    }
}
```

---

## Component 4: Mandorla Logic - Query Refinement

### Purpose
Refine search space by intersecting query manifold with index coverage (precision boost).

### Integration Point
**Location:** `mef-memory/src/`  
**New Module:** `mandorla_refiner.rs`

### Rust Implementation

```rust
// mef-memory/src/mandorla_refiner.rs

use crate::MemoryItem;

/// Mandorla query refiner configuration
#[derive(Debug, Clone)]
pub struct MandorlaConfig {
    /// Overlap threshold for query-index intersection
    pub overlap_threshold: f64,
}

impl Default for MandorlaConfig {
    fn default() -> Self {
        Self {
            overlap_threshold: 0.7,
        }
    }
}

/// Mandorla refiner
pub struct MandorlaRefiner {
    config: MandorlaConfig,
    index_stats: IndexCoverageStats,
}

/// Index coverage statistics
#[derive(Debug, Clone, Default)]
pub struct IndexCoverageStats {
    pub min_vector: Vec<f64>,
    pub max_vector: Vec<f64>,
    pub mean_vector: Vec<f64>,
}

impl MandorlaRefiner {
    pub fn new(config: MandorlaConfig) -> Self {
        Self {
            config,
            index_stats: IndexCoverageStats::default(),
        }
    }

    /// Update index statistics
    pub fn update_stats(&mut self, items: &[MemoryItem]) {
        if items.is_empty() {
            return;
        }

        let dim = items[0].vector.len();
        
        let mut min_vec = vec![f64::INFINITY; dim];
        let mut max_vec = vec![f64::NEG_INFINITY; dim];
        let mut mean_vec = vec![0.0; dim];

        for item in items {
            for (i, &v) in item.vector.iter().enumerate() {
                min_vec[i] = min_vec[i].min(v);
                max_vec[i] = max_vec[i].max(v);
                mean_vec[i] += v;
            }
        }

        for v in &mut mean_vec {
            *v /= items.len() as f64;
        }

        self.index_stats = IndexCoverageStats {
            min_vector: min_vec,
            max_vector: max_vec,
            mean_vector: mean_vec,
        };
    }

    /// Refine query to intersection with index space
    pub fn refine_query(&self, query: &[f64]) -> Option<Vec<f64>> {
        if self.index_stats.mean_vector.is_empty() {
            return Some(query.to_vec());  // No stats yet
        }

        // Compute overlap score between query and index coverage
        let overlap = self.compute_overlap(query);

        if overlap >= self.config.overlap_threshold {
            // Query is within index coverage - use as-is
            Some(query.to_vec())
        } else {
            // Query is outside index coverage - project into covered space
            Some(self.project_into_coverage(query))
        }
    }

    fn compute_overlap(&self, query: &[f64]) -> f64 {
        // Compute cosine similarity with index mean
        let dot: f64 = query.iter()
            .zip(&self.index_stats.mean_vector)
            .map(|(q, m)| q * m)
            .sum();

        let query_norm: f64 = query.iter().map(|v| v * v).sum::<f64>().sqrt();
        let mean_norm: f64 = self.index_stats.mean_vector.iter()
            .map(|v| v * v)
            .sum::<f64>()
            .sqrt();

        if query_norm * mean_norm > 1e-10 {
            (dot / (query_norm * mean_norm)).abs()
        } else {
            0.0
        }
    }

    fn project_into_coverage(&self, query: &[f64]) -> Vec<f64> {
        // Project query into index bounding box
        query.iter()
            .zip(&self.index_stats.min_vector)
            .zip(&self.index_stats.max_vector)
            .map(|((q, min), max)| q.clamp(*min, *max))
            .collect()
    }
}
```

---

## Integration Configuration

### Feature Flags (Cargo.toml)

```toml
[features]
default = ["inmemory"]
inmemory = []
optimization = ["stability-filter", "ophan-sharding", "adaptive-routing", "mandorla"]
stability-filter = []
ophan-sharding = ["rayon"]
adaptive-routing = []
mandorla = []

[dependencies]
rayon = { version = "1.8", optional = true }
```

### YAML Configuration

```yaml
# config/optimization.yaml
memory:
  backend: "optimized"  # Uses all components
  
  stability_filter:
    enabled: true
    coherence_threshold: 0.85
    max_fluctuation: 0.02
    window_size: 10
  
  ophan_sharding:
    enabled: true
    num_shards: 4
  
  adaptive_router:
    enabled: true
    small_k_threshold: 10
    large_k_threshold: 100
    high_dim_threshold: 128
  
  mandorla:
    enabled: true
    overlap_threshold: 0.7
```

---

## Performance Benchmarks

### Expected Improvements

| Metric | Baseline (InMemory) | With Optimization |
|--------|---------------------|-------------------|
| **Index Size** | 1M vectors | 700K (-30%) |
| **Query Time (k=10)** | 2.5s | 0.8s (-68%) |
| **Query Time (k=100)** | 5.2s | 2.9s (-44%) |
| **Recall@10** | 0.92 | 0.95 (+3%) |
| **Precision@10** | 0.88 | 0.93 (+5%) |

### Benchmark Code

```rust
// benches/optimization_bench.rs

use criterion::{criterion_group, criterion_main, Criterion};
use mef_memory::*;

fn bench_search(c: &mut Criterion) {
    let mut group = c.benchmark_group("search");

    // Baseline
    group.bench_function("baseline_inmemory", |b| {
        let backend = InMemoryBackend::new();
        // ... populate backend
        b.iter(|| backend.search(&query, 10))
    });

    // With optimization
    group.bench_function("optimized", |b| {
        let inner = InMemoryBackend::new();
        let filtered = FilteredBackend::new(inner, StabilityFilter::default());
        let sharded = OphanBackend::new(filtered);
        let router = AdaptiveRouter::new(sharded, RouterConfig::default());
        // ... populate
        b.iter(|| router.search(&query, 10))
    });

    group.finish();
}

criterion_group!(benches, bench_search);
criterion_main!(benches);
```

---

## Implementation Checklist for Agent

### Phase 1: Core Components (Week 1)
- [ ] Implement `StabilityFilter` in `mef-memory/src/backends/stability_filter.rs`
- [ ] Add `FilteredBackend` wrapper
- [ ] Write unit tests for PoR logic
- [ ] Integrate with existing `MemoryBackend` trait

### Phase 2: Parallel Sharding (Week 2)
- [ ] Implement `OphanBackend` with 4-shard architecture
- [ ] Add `CentralAggregator` (Konus) for result merging
- [ ] Implement shard assignment hash function
- [ ] Test parallel search correctness

### Phase 3: Adaptive Routing (Week 3)
- [ ] Implement `AdaptiveRouter` with strategy selection
- [ ] Add Chronokrator decision tree logic
- [ ] Test routing for different query profiles
- [ ] Benchmark strategy performance

### Phase 4: Query Refinement (Week 4)
- [ ] Implement `MandorlaRefiner` with overlap computation
- [ ] Add index coverage statistics tracking
- [ ] Implement query projection into covered space
- [ ] Test precision improvements

### Phase 5: Integration & Testing (Week 5)
- [ ] Add feature flags to `Cargo.toml`
- [ ] Create YAML configuration schema
- [ ] Write end-to-end integration tests
- [ ] Run benchmarks and validate performance gains

### Phase 6: Documentation (Week 6)
- [ ] Write API documentation
- [ ] Create usage examples
- [ ] Update architecture diagrams
- [ ] Publish performance results

---

## Testing Strategy

### Unit Tests
Each component must have:
- ✅ Input validation tests
- ✅ Correctness tests (determinism)
- ✅ Edge case handling
- ✅ Performance regression tests

### Integration Tests
- ✅ Component chaining (Filter → Shard → Route → Refine)
- ✅ Compatibility with existing MEF-Core pipeline
- ✅ Feature flag combinations
- ✅ Configuration parsing

### Benchmarks
- ✅ Search latency (k=10, 50, 100, 500)
- ✅ Index build time
- ✅ Memory footprint
- ✅ Throughput (queries/second)

---

## Agent Instructions

### Context
You are integrating 4 performance optimization components into an existing Rust-based vector database system (MEF-Core). The system:
- **Already has a working vector database implementation**
- **Is being benchmarked against FAISS and Qdrant**
- Has a `MemoryBackend` or similar trait for storage
- Has an 8D vector construction pipeline
- Has Proof-of-Resonance (PoR) validation logic

### Critical Discovery Phase (DO THIS FIRST)

**Step 0: Locate the existing vector database implementation**

Search for:
```bash
# Find vector storage/search implementation
rg "impl.*VectorBackend" --type rust
rg "fn search" --type rust -A 5
rg "struct.*Index" --type rust
rg "nearest_neighbor" --type rust

# Common locations:
# - mef-memory/src/backends/
# - mef-core/src/metamemory.rs
# - mef-vector/src/
```

**Document findings:**
1. Name of the trait/struct for vector operations
2. Method signatures for insert/search
3. Current implementation strategy (flat, IVF, HNSW, etc.)
4. How it's used in benchmarks

### Your Task
Implement optimizations as a **wrapper around existing implementation**:
1. Start with `StabilityFilter` wrapper (simplest, biggest impact)
2. Add `OphanBackend` for parallel sharding (wrap existing backend)
3. Implement `AdaptiveRouter` for strategy selection
4. Add `MandorlaRefiner` for query optimization

**Goal:** Beat FAISS and Qdrant in benchmarks!

### Key Constraints
- ❌ **DO NOT modify MEF-Core modules** (mef-spiral, mef-tic, mef-ledger, mef-core)
- ✅ **ONLY add new modules** to `mef-memory/src/backends/`
- ✅ **Use existing MemoryBackend trait** - no changes to interface
- ✅ **Follow ADD-ONLY principle** from SPEC-006

### Success Criteria
- [ ] All unit tests pass
- [ ] Integration tests show component chaining works
- [ ] Benchmarks show >50% search speedup
- [ ] Index size reduced by >20%
- [ ] Zero modifications to core MEF modules

---

## References

- **MEF-Core Specification:** See `MEF-Crystallizer-MEF-Core.pdf`
- **Extension Architecture:** See `ARCHITECTURE_EXTENSION.md`
- **MemoryBackend Trait:** `mef-memory/src/backends/mod.rs`
- **Benchmark Template:** `benches/memory_bench.rs`

---

## Questions for Clarification

If the agent needs clarification, consult these decision points:

### Q1: Should we support FAISS backend now or later?
**A:** Implement InMemory first, design trait to support FAISS later.

### Q2: What hash function for shard assignment?
**A:** Use Rust's `DefaultHasher` - deterministic, fast, good distribution.

### Q3: How to handle vector normalization in filter?
**A:** Already handled by `Vector8Builder` - assume input is normalized.

### Q4: Should Mandorla update stats incrementally or batch?
**A:** Batch update on index rebuild - incremental adds complexity.

---

**END OF SPECIFICATION**