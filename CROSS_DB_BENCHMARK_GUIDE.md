# Cross-Database Benchmark Infrastructure

This document describes the enterprise-ready CI/CD infrastructure for running comprehensive cross-database benchmarks in the MEF-Core project.

## Overview

The cross-database benchmark infrastructure provides:

1. **CLI Tool** (`cross-db-bench`): A command-line binary for running benchmarks across multiple vector database implementations
2. **Docker Services**: Pre-configured docker-compose setup for benchmark services
3. **CI Integration**: Automated benchmark execution in GitHub Actions
4. **Detailed Reporting**: JSON and console output with comprehensive metrics

## Components

### 1. Cross-DB Benchmark CLI (`cross-db-bench`)

Located in `mef-bench/src/bin/cross_db_bench.rs`, this tool:

- Supports multiple vector database drivers (FAISS, Elasticsearch, Qdrant, Milvus, Weaviate, Pinecone, MEF)
- Generates synthetic benchmark datasets
- Computes ground truth with exact search
- Measures latency, throughput, and accuracy (recall)
- Produces JSON and human-readable reports

**Usage:**

```bash
# Test specific drivers
cargo run --package mef-bench --bin cross-db-bench --release faiss elastic qdrant

# Test all available drivers
cargo run --package mef-bench --bin cross-db-bench --release

# Configure via environment variables
BENCH_NUM_VECTORS=50000 \
BENCH_NUM_QUERIES=100 \
BENCH_K=10 \
BENCH_METRIC=cosine \
BENCH_BATCH_SIZE=5000 \
BENCH_OUTPUT=results.json \
cargo run --package mef-bench --bin cross-db-bench --release faiss
```

**Environment Variables:**

- `BENCH_NUM_VECTORS`: Number of vectors to index (default: 10000, CI uses 50000)
- `BENCH_NUM_QUERIES`: Number of search queries to run (default: 100)
- `BENCH_DIMENSION`: Vector dimension (default: 128)
- `BENCH_K`: Number of neighbors to retrieve (default: 10)
- `BENCH_METRIC`: Distance metric - `cosine`, `l2`, or `ip` (default: cosine)
- `BENCH_BATCH_SIZE`: Batch size for upserts (default: 1000, CI uses 5000)
- `BENCH_OUTPUT`: Output file path (default: benchmark_results.json)

**Driver-Specific Configuration:**

- **Elasticsearch**: `ELASTIC_URL` (e.g., http://localhost:9200)
- **Qdrant**: `QDRANT_URL` (e.g., http://localhost:6333)
- **Milvus**: `MILVUS_HOST` and `MILVUS_PORT` (e.g., localhost:19530)
- **Weaviate**: `WEAVIATE_URL` (e.g., http://localhost:8080)
- **Pinecone**: `PINECONE_API_KEY` and `PINECONE_ENV`
- **MEF**: `MEF_BASE_URL` (e.g., http://localhost:8080)

### 2. Docker Compose Configuration

`docker-compose.bench.yml` provides pre-configured services:

- **Elasticsearch** 8.11.0 (port 9200)
- **Qdrant** 1.7.4 (port 6333)
- **Milvus** 2.3.4 (ports 19530, 9091) with etcd and MinIO
- **Weaviate** 1.22.4 (port 8080)

**Start services:**

```bash
docker compose -f docker-compose.bench.yml up -d
```

**Stop services:**

```bash
docker compose -f docker-compose.bench.yml down -v
```

### 3. CI/CD Integration

The GitHub Actions workflow (`.github/workflows/rust-ci.yml`) includes two benchmark jobs:

#### Performance Benchmarks

Runs Criterion benchmarks for MEF-Core components:

```yaml
benchmark:
  name: Performance Benchmarks
  runs-on: ubuntu-latest
  steps:
    - Run criterion benchmarks
    - Upload criterion results
```

#### Cross-Database Benchmarks

Runs comprehensive cross-database comparisons:

```yaml
cross-db-benchmark:
  name: Cross-Database Benchmarks
  runs-on: ubuntu-latest
  steps:
    - Build cross-db-bench binary
    - Start benchmark services (optional)
    - Run cross-database benchmarks
    - Upload benchmark results
```

**Current Configuration:**

The CI currently runs with FAISS baseline (no external services required). Additional drivers can be enabled by:

1. Uncommenting service startup steps
2. Adding driver names to the benchmark command
3. Setting appropriate environment variables

## Benchmark Report Format

The tool generates two outputs:

### 1. Console Output

Human-readable table with key metrics:

```
📊 Benchmark Results Summary
============================

Driver          Status     P50 (ms)     P95 (ms)     Recall@10    QPS
───────────────────────────────────────────────────────────────────
faiss-baseline  ✅ success  0.32         0.34         97.8%        2948
elastic         ✅ success  1.23         2.45         95.2%        813
qdrant          ✅ success  0.89         1.67         96.5%        1124

🏆 Winners:
  ⚡ Fastest (P50): faiss-baseline
  🎯 Most Accurate: faiss-baseline
  🚀 Highest Throughput: faiss-baseline
```

### 2. JSON Report

Detailed JSON output with all metrics:

```json
{
  "timestamp": "2025-10-15T19:52:25Z",
  "config": {
    "num_vectors": 5000,
    "num_queries": 50,
    "dimension": 128,
    "k": 10,
    "metric": "cosine"
  },
  "results": [
    {
      "driver_name": "faiss-baseline",
      "metric": "cosine",
      "status": "success",
      "connect_time_ms": 0.0,
      "upsert_time_ms": 1.2,
      "search_time_ms": 17.0,
      "avg_search_latency_ms": 0.32,
      "p50_search_latency_ms": 0.32,
      "p95_search_latency_ms": 0.34,
      "p99_search_latency_ms": 0.59,
      "recall_at_10": 0.978,
      "vectors_per_second": 4162470,
      "queries_per_second": 2948
    }
  ],
  "summary": {
    "total_drivers_tested": 1,
    "successful_drivers": 1,
    "failed_drivers": 0,
    "fastest_driver": "faiss-baseline",
    "highest_recall_driver": "faiss-baseline",
    "highest_throughput_driver": "faiss-baseline"
  }
}
```

## Metrics Explained

- **P50 (median) latency**: Middle value of search latencies
- **P95 latency**: 95th percentile - 95% of queries are faster
- **P99 latency**: 99th percentile - 99% of queries are faster
- **Recall@k**: Percentage of true nearest neighbors retrieved
- **QPS**: Queries per second (throughput)
- **Vectors/second**: Ingestion throughput

## Available Drivers

### Implemented and Tested

1. **FAISS Baseline** (`faiss`) - Brute-force exact search, no external service required
2. **Qdrant** (`qdrant`) - Requires Qdrant service
3. **Weaviate** (`weaviate`) - Requires Weaviate service
4. **MEF Optimized** (`mef`) - MEF API with optimization components (when enabled)

### Implemented (Require Additional Configuration)

4. **Elasticsearch** (`elastic`) - Requires dense_vector plugin configuration
5. **Milvus** (`milvus`) - Requires gRPC client integration
6. **MEF** (`mef`) - Requires MEF API server running
7. **Pinecone** (`pinecone`) - Requires API key and environment

## Future Enhancements

### Planned Improvements

1. **Enhanced Driver Support**:
   - Fix Elasticsearch dense_vector mapping
   - Implement Milvus gRPC client
   - Add MEF API integration tests
   - Support Pinecone serverless

2. **Advanced Benchmarking**:
   - Multi-metric comparison (cosine, l2, ip)
   - Scalability tests (varying dataset sizes)
   - Concurrent query benchmarks
   - Resource utilization metrics (memory, CPU)
   - **Optimization component performance comparison**

3. **Reporting Enhancements**:
   - Historical trend analysis
   - Comparison against baselines
   - Performance regression detection
   - Grafana dashboard integration
   - **Component-level performance breakdown**

4. **CI/CD Improvements**:
   - Parallel driver execution
   - Conditional driver testing (based on PR changes)
   - Benchmark result caching
   - Performance gates (fail on regression)
   - **Automated optimization validation**

## MEF Optimization Components

The MEF driver can leverage 4 optimization components (per `mef_integration_spec.md`):

### 1. Kosmokrator - Stability Filter
Reduces index size by 20-40% by filtering unstable vectors using Proof-of-Resonance logic.

### 2. O.P.H.A.N. Array - Parallel Sharding
Provides 3-4x search speedup via 4-shard parallel architecture.

### 3. Chronokrator - Adaptive Router
Dynamically selects search strategy (Exact/Approximate/Hybrid) based on query profile.

### 4. Mandorla Logic - Query Refinement
Improves precision by 5% through query-space projection.

### Testing Optimizations

To benchmark with optimizations enabled:

```bash
# Enable all optimization features
MEF_OPTIMIZATION_ENABLED=true \
cargo run --package mef-bench --bin cross-db-bench --release --features optimization mef

# Or configure via YAML
cat > /tmp/bench_config.yaml << EOF
mef:
  extension:
    memory:
      optimization:
        enabled: true
        stability_filter:
          enabled: true
        ophan_sharding:
          enabled: true
        adaptive_router:
          enabled: true
        mandorla:
          enabled: true
EOF

MEF_CONFIG=/tmp/bench_config.yaml \
cargo run --package mef-bench --bin cross-db-bench --release --features optimization mef
```

### Expected Performance Gains

| Metric | Baseline | With Optimization | Improvement |
|--------|----------|-------------------|-------------|
| Index Size | 1M vectors | 700K vectors | -30% |
| Query Time (k=10) | 2.5s | 0.8s | -68% |
| Query Time (k=100) | 5.2s | 2.9s | -44% |
| Recall@10 | 92% | 95% | +3% |
| Precision@10 | 88% | 93% | +5% |

## Development Guide

### Adding a New Driver

1. Implement `VectorStoreDriver` trait in `mef-bench/src/`
2. Add driver to registry in `mef-bench/src/lib.rs`
3. Add tests for the driver
4. Update docker-compose if service is needed
5. Document driver configuration

### Running Locally

```bash
# Build the binary
cargo build --package mef-bench --bin cross-db-bench --release

# Run with default settings
./target/release/cross-db-bench faiss

# Run with custom configuration
BENCH_NUM_VECTORS=1000 \
BENCH_NUM_QUERIES=20 \
./target/release/cross-db-bench faiss

# With multiple drivers
QDRANT_URL=http://localhost:6333 \
./target/release/cross-db-bench faiss qdrant
```

### Testing in CI

The benchmark runs automatically on:

- Push to `main` or `master`
- Pull requests to `main` or `master`
- Push to `copilot/**` branches
- Manual workflow dispatch

Results are uploaded as GitHub Actions artifacts.

## Troubleshooting

### Driver Connection Failures

- Check service health endpoints
- Verify environment variables are set
- Ensure ports are not in use
- Check firewall/network settings

### Low Recall Scores

- Verify metric is consistent (cosine vs l2)
- Check vector normalization
- Increase k value for more results
- Review driver implementation

### Performance Issues

- Reduce BENCH_NUM_VECTORS for faster testing
- Increase BENCH_BATCH_SIZE for better throughput
- Use release build for accurate measurements
- Ensure adequate system resources

### Scaling to Larger Datasets

For testing with 100K vectors or more:

```bash
# 100K vectors with 10K batch size
BENCH_NUM_VECTORS=100000 \
BENCH_BATCH_SIZE=10000 \
BENCH_NUM_QUERIES=50 \
./target/release/cross-db-bench faiss mef qdrant

# For even larger datasets, adjust batch size proportionally
# Rule of thumb: batch_size = num_vectors / 10 to num_vectors / 20
```

**Note**: The CI is configured to run with 50K vectors and 5K batch size for comprehensive testing while maintaining reasonable runtime.

## References

- [Benchmark Driver README](mef-bench/README.md)
- [GitHub Actions Workflow](.github/workflows/rust-ci.yml)
- [Docker Compose Config](docker-compose.bench.yml)
- [Migration Summary](BENCHMARK_MIGRATION_SUMMARY.md)
