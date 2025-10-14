# Environment Variables Reference

This document provides comprehensive documentation for all environment variables used in the MEF-Core benchmark and testing infrastructure.

## Table of Contents

- [Benchmark Configuration](#benchmark-configuration)
- [Service URLs](#service-urls)
- [Connection Settings](#connection-settings)
- [Authentication](#authentication)
- [Golden Test Configuration](#golden-test-configuration)
- [Feature Flags](#feature-flags)
- [Advanced Configuration](#advanced-configuration)

---

## Benchmark Configuration

### BENCH_POINTS
- **Type**: Integer
- **Default**: `100000`
- **Range**: 100 - 10,000,000
- **Description**: Number of data points to index during benchmark runs. Higher values provide more accurate performance metrics but take longer to execute.
- **Example**: `BENCH_POINTS=50000`

### BENCH_Q
- **Type**: Integer
- **Default**: `200`
- **Range**: 1 - 10,000
- **Description**: Number of query vectors to use for search benchmarks. More queries provide better statistical accuracy for latency measurements.
- **Example**: `BENCH_Q=500`

### BENCH_K
- **Type**: Integer
- **Default**: `10`
- **Range**: 1 - 1,000
- **Description**: Number of nearest neighbors to retrieve per search query (the "k" in k-NN).
- **Example**: `BENCH_K=20`

### UPSERT_BATCH
- **Type**: Integer
- **Default**: `2000`
- **Range**: 1 - 10,000
- **Description**: Batch size for bulk ingestion operations. Larger batches may be more efficient but require more memory.
- **Example**: `UPSERT_BATCH=5000`

### BENCH_TIMEOUT_SECONDS
- **Type**: Float
- **Default**: `1200.0` (20 minutes)
- **Range**: 10.0 - 7200.0
- **Description**: Maximum time in seconds to wait for benchmark operations to complete before timing out.
- **Example**: `BENCH_TIMEOUT_SECONDS=600.0`

### COMPARE_LIMIT
- **Type**: Integer
- **Default**: `500`
- **Range**: 0 - unlimited
- **Description**: Limit the number of points and queries for cross-database comparison benchmarks. Set to 0 to use full BENCH_POINTS and BENCH_Q values.
- **Example**: `COMPARE_LIMIT=1000`

---

## Service URLs

### QUALITY_BASE_URL
- **Type**: URL
- **Default**: `http://api:8080`
- **Schemes**: `http`, `https`
- **Description**: Base URL for the MEF-Core API service. Used by benchmark scripts to communicate with the quality service.
- **Example**: `QUALITY_BASE_URL=http://localhost:8080`

### MEF_BASE_URL
- **Type**: URL
- **Default**: `http://localhost:8080`
- **Schemes**: `http`, `https`
- **Description**: Base URL for the MEF HTTP driver in comparison benchmarks.
- **Example**: `MEF_BASE_URL=http://api:8080`

### QDRANT_URL
- **Type**: URL
- **Default**: `http://qdrant:6333`
- **Schemes**: `http`, `https`
- **Description**: URL for the Qdrant vector database instance.
- **Example**: `QDRANT_URL=http://localhost:6333`

### FAISS_URL
- **Type**: URL
- **Default**: `http://localhost:8090`
- **Schemes**: `http`, `https`
- **Description**: URL for the FAISS HTTP API service used in comparison benchmarks.
- **Example**: `FAISS_URL=http://faiss-api:8090`

### MILVUS_HOST
- **Type**: String
- **Default**: `milvus`
- **Description**: Hostname or IP address of the Milvus vector database instance.
- **Example**: `MILVUS_HOST=localhost`

### MILVUS_PORT
- **Type**: Integer
- **Default**: `19530`
- **Range**: 1 - 65535
- **Description**: gRPC port for the Milvus vector database.
- **Example**: `MILVUS_PORT=19530`

---

## Connection Settings

### BENCH_CONNECT_TIMEOUT
- **Type**: Float
- **Default**: `240.0` (4 minutes)
- **Range**: 1.0 - 600.0
- **Description**: Maximum time in seconds to wait for initial service connections during benchmark startup.
- **Example**: `BENCH_CONNECT_TIMEOUT=120.0`

### BENCH_CONNECT_RETRY_DELAY
- **Type**: Float
- **Default**: `2.0`
- **Range**: 0.1 - 60.0
- **Description**: Delay in seconds between connection retry attempts.
- **Example**: `BENCH_CONNECT_RETRY_DELAY=5.0`

### HTTPX_TIMEOUT
- **Type**: Float
- **Default**: `30.0`
- **Range**: 1.0 - 300.0
- **Description**: HTTP request timeout in seconds for httpx-based clients.
- **Example**: `HTTPX_TIMEOUT=60.0`

---

## Authentication

### AUTH_TOKEN_REQUIRED
- **Type**: Boolean
- **Default**: `false`
- **Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Description**: Whether API authentication is required. When false, token validation is skipped.
- **Example**: `AUTH_TOKEN_REQUIRED=true`

### MEF_API_TOKEN
- **Type**: String (Secret)
- **Default**: Empty
- **Description**: Authentication token for MEF-Core API requests. Required when AUTH_TOKEN_REQUIRED is true.
- **Example**: `MEF_API_TOKEN=your-secret-token-here`

### QUALITY_TOKEN
- **Type**: String (Secret)
- **Default**: Empty
- **Description**: Authentication token for quality service requests.
- **Example**: `QUALITY_TOKEN=your-quality-token-here`

---

## Golden Test Configuration

### GOLDEN_COUNT
- **Type**: Integer
- **Default**: `30`
- **Range**: 1 - 1,000
- **Description**: Number of golden test samples to generate and validate.
- **Example**: `GOLDEN_COUNT=50`

### GOLDEN_MIN_OK
- **Type**: Integer
- **Default**: `10`
- **Range**: 1 - unlimited
- **Description**: Minimum number of successful golden test runs required for the test suite to pass.
- **Example**: `GOLDEN_MIN_OK=25`

### GOLDEN_ATTEMPTS_FACTOR
- **Type**: Integer
- **Default**: `8`
- **Range**: 1 - 100
- **Description**: Multiplier for the maximum number of attempts per golden test sample. Total attempts = GOLDEN_COUNT * GOLDEN_ATTEMPTS_FACTOR.
- **Example**: `GOLDEN_ATTEMPTS_FACTOR=10`

### GOLDEN_SEED
- **Type**: Integer
- **Default**: `1337`
- **Range**: 0 - unlimited
- **Description**: Random seed for golden test generation to ensure reproducibility.
- **Example**: `GOLDEN_SEED=42`

### GOLDEN_HOLD_POLICY
- **Type**: String
- **Default**: `skip`
- **Values**: `skip`, `block`, `fail`
- **Description**: Policy for handling proof-of-resonance holds during golden tests.
  - `skip`: Skip holds and continue testing
  - `block`: Wait for holds to complete
  - `fail`: Fail test if holds occur
- **Example**: `GOLDEN_HOLD_POLICY=skip`

---

## Feature Flags

### BENCH_COMPARE
- **Type**: Boolean
- **Default**: `true`
- **Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Description**: Enable cross-database comparison benchmarks.
- **Example**: `BENCH_COMPARE=1`

### STRICT_READPATH
- **Type**: Boolean
- **Default**: `true`
- **Values**: `true`, `false`, `1`, `0`, `yes`, `no`, `on`, `off`
- **Description**: Enable strict validation of read paths during benchmarks.
- **Example**: `STRICT_READPATH=false`

---

## Advanced Configuration

### TARGETS
- **Type**: Comma-separated list
- **Default**: `mef,faiss,qdrant,milvus`
- **Allowed Values**: `mef`, `mef-core`, `mef-http`, `faiss`, `faiss-inproc`, `faiss-http`, `qdrant`, `milvus`, `weaviate`, `elasticsearch`, `pinecone`
- **Description**: List of vector store targets to include in comparison benchmarks.
- **Example**: `TARGETS=mef,faiss,qdrant`

### BENCH_TARGETS
- **Type**: Comma-separated list
- **Default**: `mef,faiss,qdrant,milvus`
- **Allowed Values**: Same as TARGETS
- **Description**: Specific targets for benchmark execution. Typically same as TARGETS.
- **Example**: `BENCH_TARGETS=mef-core,faiss-inproc`

### REQUIRED_TARGETS
- **Type**: Comma-separated list
- **Default**: `mef,faiss,qdrant`
- **Allowed Values**: Same as TARGETS
- **Description**: Minimum set of targets that must succeed for benchmarks to pass. Other targets are optional.
- **Example**: `REQUIRED_TARGETS=mef,faiss`

### RECALL_EFSEARCH
- **Type**: Integer
- **Default**: `128`
- **Range**: 1 - 1,000
- **Description**: HNSW ef_search parameter for recall evaluation benchmarks. Higher values improve recall at the cost of search performance.
- **Example**: `RECALL_EFSEARCH=256`

### HNSW_EF_SEARCH
- **Type**: Integer
- **Default**: `64`
- **Range**: 1 - 1,000
- **Description**: HNSW ef_search parameter for regular benchmark searches.
- **Example**: `HNSW_EF_SEARCH=128`

### QUALITY_COLLECTION
- **Type**: String
- **Default**: `quality`
- **Description**: Name of the vector collection used for quality metrics.
- **Example**: `QUALITY_COLLECTION=benchmark_collection`

### ANN_METRIC
- **Type**: String
- **Default**: `cosine`
- **Values**: `cosine`, `euclidean`, `dot`
- **Description**: Distance metric for approximate nearest neighbor search.
- **Example**: `ANN_METRIC=euclidean`

---

## Usage Examples

### Minimal Local Testing
```bash
export BENCH_POINTS=1000
export BENCH_Q=50
export COMPARE_LIMIT=100
export TARGETS=mef,faiss
python tests/bench/bench_runner.py
```

### Full CI Configuration
```bash
export BENCH_POINTS=100000
export BENCH_Q=200
export BENCH_K=10
export BENCH_COMPARE=1
export TARGETS=mef,faiss,qdrant,milvus
export BENCH_TIMEOUT_SECONDS=1200
export QUALITY_BASE_URL=http://api:8080
docker compose -f docker-compose.ci.yml up
```

### High-Precision Benchmarking
```bash
export BENCH_POINTS=500000
export BENCH_Q=1000
export BENCH_K=50
export RECALL_EFSEARCH=512
export HNSW_EF_SEARCH=256
export BENCH_TIMEOUT_SECONDS=3600
python tests/bench/bench_runner.py
```

---

## Validation

All environment variables are validated by the `preflight_check.py` script before benchmark execution. The script will:

1. Check that all required variables are set or have sensible defaults
2. Validate types (int, float, bool, URL)
3. Enforce range constraints (min/max values)
4. Verify URL formats and schemes
5. Validate comma-separated lists against allowed values

To run validation manually:
```bash
python MEF-Core_v1.0/tests/bench/preflight_check.py
```

---

## Troubleshooting

### Common Issues

**Issue**: "ERROR: Invalid environment variable BENCH_POINTS: must be >= 100"
- **Solution**: Ensure BENCH_POINTS is at least 100. The minimum is enforced to ensure meaningful benchmark results.

**Issue**: "ERROR: Invalid environment variable QUALITY_BASE_URL: invalid URL format"
- **Solution**: URL must include a scheme (http:// or https://). Example: `http://api:8080` not `api:8080`

**Issue**: "ERROR: Invalid environment variable TARGETS: invalid values ['invalid']"
- **Solution**: Check that all target names are in the allowed list. See TARGETS documentation above for valid values.

**Issue**: Pre-flight validation passes but benchmark fails to connect
- **Solution**: Verify that services are actually running and accessible at the configured URLs. Use curl to test:
  ```bash
  curl http://localhost:8080/healthz
  curl http://localhost:6333/readyz
  ```

---

## See Also

- [CI/CD Pipeline Documentation](../CI_IMPROVEMENTS_SUMMARY.md)
- [Benchmark Suite Documentation](README_bench.md)
- [Environment Validator Module](tests/bench/env_validator.py)
