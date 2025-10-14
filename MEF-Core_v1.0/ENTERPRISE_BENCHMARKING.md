# Enterprise Cross-DB Benchmarking Guide

## Overview

The MEF cross-database benchmarking infrastructure provides enterprise-ready performance comparison across multiple vector database implementations:

### Supported Databases

**Pure/In-Process Drivers:**
- `mef-core` - MEF native in-process implementation
- `faiss-inproc` - FAISS in-process baseline

**HTTP/API Drivers:**
- `mef-http` - MEF HTTP API
- `faiss-http` - FAISS HTTP microservice

**External Service Drivers:**
- `qdrant` - Qdrant vector database
- `milvus` - Milvus vector database  
- `weaviate` - Weaviate vector database
- `elastic` - Elasticsearch with vector search
- `pinecone` - Pinecone cloud service

## Architecture

### Driver Registry

The system uses a unified driver registry that merges:
1. **Compare drivers** (`tests/bench/compare/drivers`) - Simplified interface for pure/HTTP testing
2. **External drivers** (`src/bench/drivers`) - Full-featured service integrations

An adapter pattern bridges the two interfaces, allowing seamless testing across all implementations.

### Metrics Collected

For each database, the system measures:
- **Recall@K** - Accuracy of top-K results vs ground truth
- **Latency** - p50, p95, p99 response times in milliseconds
- **Throughput** - Queries per second (QPS)
- **Errors** - Count of failed queries

## Configuration

### Environment Variables

| Variable | Purpose | Default | Example |
|----------|---------|---------|---------|
| `BENCH_COMPARE` | Enable compare harness | `auto` | `1` |
| `TARGETS` | Comma-separated driver list | `mef,faiss` | `mef-core,faiss-inproc,qdrant` |
| `COMPARE_LIMIT` | Max corpus/query size | `0` (unlimited) | `500` |
| `REQUIRED_TARGETS` | Drivers that must succeed | (none) | `mef,faiss,qdrant` |
| `BENCH_POINTS` | Dataset size | `100000` | `10000` |
| `BENCH_Q` | Number of queries | `200` | `100` |
| `BENCH_K` | Top-K for recall | `10` | `10` |
| `BENCH_METRIC` | Distance metric | `cosine` | `cosine` or `l2` |
| `UPSERT_BATCH` | Bulk insert batch size | `1000` | `2000` |
| `BENCH_CONNECT_TIMEOUT` | Service connection timeout (seconds) | `240` | `120` |
| `BENCH_CONNECT_RETRY_DELAY` | Retry delay (seconds) | `2.0` | `1.0` |

### Service Connection

Each external service requires specific environment variables:

**Qdrant:**
```bash
QDRANT_URL=http://qdrant:6333
```

**Milvus:**
```bash
MILVUS_HOST=milvus
MILVUS_PORT=19530
```

**Weaviate:**
```bash
WEAVIATE_URL=http://weaviate:8080
```

**Elasticsearch:**
```bash
ELASTIC_URL=http://elasticsearch:9200
```

**Pinecone:**
```bash
PINECONE_API_KEY=<your-key>
PINECONE_ENV=<your-environment>
PINECONE_INDEX=<index-name>
```

## Deployment Scenarios

### 1. Local Development

Test pure drivers without external services:

```bash
cd MEF-Core_v1.0
export PYTHONPATH="$(pwd)/src:$(pwd)"
export BENCH_COMPARE=1
export TARGETS=mef-core,faiss-inproc
export COMPARE_LIMIT=128
python -m tests.bench.compare
```

**Output:**
- `assets/bench/compare.json` - Structured metrics
- `assets/bench/compare.md` - Human-readable report

### 2. Docker Compose Testing

Test with external services via Docker Compose:

```bash
# Start services (includes MEF, FAISS, Qdrant, and Milvus)
docker compose -f docker-compose.ci.yml --profile compare up -d

# Run comparison with all databases
export PYTHONPATH="$(pwd)/MEF-Core_v1.0/src:$(pwd)/MEF-Core_v1.0"
export BENCH_COMPARE=1
export TARGETS=mef,faiss,qdrant,milvus
export COMPARE_LIMIT=500
export QDRANT_URL=http://localhost:6333
export MILVUS_HOST=localhost
export MILVUS_PORT=19530
export MEF_BASE_URL=http://localhost:8080
python -m MEF-Core_v1.0.tests.bench.compare

# Cleanup
docker compose -f docker-compose.ci.yml down -v
```

### 3. CI/CD Integration

The GitHub Actions workflow automatically runs cross-DB benchmarks:

**Workflow Steps:**
1. Starts MEF API, FAISS service, Qdrant, Milvus, and QA container
2. Runs bench_runner.py, recall_eval.py, golden tests
3. Executes cross-DB compare with `mef,faiss,qdrant,milvus`
4. Tests pure drivers: `mef-core,faiss-inproc`
5. Tests HTTP drivers: `mef-http,faiss-http`
6. Uploads 6 artifacts: `compare.json`, `compare.md`, `compare_pure.json`, `compare_pure.md`, `compare_http.json`, `compare_http.md`

**Quality Gates:**
- At least 2 successful targets required
- All `REQUIRED_TARGETS` must pass (typically: `mef,faiss,qdrant`)
- Artifacts must exist and be non-empty

### 4. Production Monitoring

For production benchmarking:

```bash
# High-volume test
export BENCH_COMPARE=1
export TARGETS=mef,qdrant,milvus
export BENCH_POINTS=1000000
export BENCH_Q=1000
export BENCH_K=100
export UPSERT_BATCH=5000
export REQUIRED_TARGETS=mef

python -m tests.bench.compare
```

## Failure Handling

### Graceful Degradation

The system handles service unavailability gracefully:
- **Missing credentials** → Driver skipped with reason "not configured"
- **Connection timeout** → Driver skipped with reason "connection failed"
- **Service error** → Driver skipped with error message

Comparison succeeds as long as ≥2 targets complete successfully.

### Required Targets

Use `REQUIRED_TARGETS` to enforce specific drivers:

```bash
export REQUIRED_TARGETS=mef,qdrant
```

If any required target skips or fails, the comparison exits with code 2.

### Connection Retry

External services get automatic retry logic:
- Default timeout: 240 seconds
- Retry delay: 2 seconds
- Non-retryable: "not configured", "missing credentials"

## Output Artifacts

### compare.json

```json
{
  "commit": "abc123...",
  "dataset": {
    "points": 500,
    "dim": 5,
    "queries": 500,
    "k": 10,
    "metric": "cosine"
  },
  "targets": [
    {
      "name": "mef-core",
      "token": "mef-core",
      "status": "ok",
      "recall@K": 0.987654,
      "p50_ms": 1.234,
      "p95_ms": 2.345,
      "p99_ms": 3.456,
      "qps": 789.012,
      "errors": 0
    },
    {
      "name": "qdrant",
      "token": "qdrant",
      "status": "skipped",
      "reason": "connection timeout after 240s"
    }
  ],
  "errors": []
}
```

### compare.md

```markdown
# Vector Store Compare Benchmark

*Commit:* `abc123...`  
*Dataset:* 500 points · dim=5 · queries=500 · k=10 · metric=cosine

## Summary

| Target | Status | recall@K | p50 (ms) | p95 (ms) | p99 (ms) | QPS | Errors | Reason |
|---|---|---|---|---|---|---|---|---|
| mef-core | ok | 0.988 | 1.23 | 2.35 | 3.46 | 789.0 | 0 |  |
| qdrant | skipped | 0.000 | 0.00 | 0.00 | 0.00 | 0.0 | 0 | connection timeout after 240s |

## Sorted by p50 latency (lower is better)

...
```

## Troubleshooting

### Common Issues

**Issue:** "compare requires at least two successful targets"  
**Solution:** Ensure services are running and `TARGETS` includes available drivers

**Issue:** "required compare targets failed: qdrant (skipped)"  
**Solution:** Check service connectivity or remove from `REQUIRED_TARGETS`

**Issue:** Driver exits with "missing credentials"  
**Solution:** Set required environment variables (e.g., `PINECONE_API_KEY`)

**Issue:** Timeout connecting to service  
**Solution:** Increase `BENCH_CONNECT_TIMEOUT` or verify service health

### Debugging

Enable verbose output:
```bash
python -m tests.bench.compare 2>&1 | tee compare-debug.log
```

Check generated artifacts:
```bash
cat assets/bench/compare.json | jq '.targets[] | select(.status != "ok")'
```

Validate service health:
```bash
curl -f http://localhost:8080/healthz  # MEF
curl -f http://localhost:6333/readyz    # Qdrant
curl -f http://localhost:19530/health   # Milvus
```

## Performance Tuning

### Batch Sizing

Adjust `UPSERT_BATCH` based on dataset and service:
- **Small datasets** (<10K): 500-1000
- **Medium datasets** (10K-100K): 2000-5000
- **Large datasets** (>100K): 5000-10000

### Connection Pooling

For HTTP drivers, increase worker count:
```bash
UVICORN_WORKERS=4  # For MEF API
```

### Query Optimization

Reduce workload for CI:
```bash
COMPARE_LIMIT=500      # Limit dataset size
BENCH_K=10             # Reasonable top-K
BENCH_WARMUP=10        # Warmup queries
```

## Adding New Drivers

### External Service Driver

1. Create driver in `src/bench/drivers/`:

```python
from bench.drivers.base import VectorStoreDriver, DriverUnavailable

class MyServiceDriver(VectorStoreDriver):
    name = "myservice"
    
    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric=metric)
        self._url = os.getenv("MYSERVICE_URL")
        if not self._url:
            raise DriverUnavailable("myservice", "MYSERVICE_URL not configured")
    
    def connect(self) -> None:
        # Connect to service
        pass
    
    def clear(self, namespace: str) -> None:
        # Clear namespace
        pass
    
    def upsert(self, items, namespace: str, batch_size: int = 1000) -> None:
        # Bulk insert
        pass
    
    def search(self, query, k: int, namespace: str):
        # Vector search
        pass
```

2. Register in `src/bench/drivers/__init__.py`:

```python
from .myservice_driver import MyServiceDriver

DRIVER_REGISTRY = {
    # ...
    "myservice": MyServiceDriver,
}
```

3. Test:

```bash
export MYSERVICE_URL=http://localhost:9000
export TARGETS=mef,myservice
python -m tests.bench.compare
```

## Best Practices

### Enterprise Deployment

1. **Pin Dependencies** - Use exact versions in `requirements.txt`
2. **Monitor Timeouts** - Set appropriate `BENCH_CONNECT_TIMEOUT`
3. **Resource Limits** - Configure Docker memory/CPU limits
4. **Error Alerting** - Parse `compare.json` for `status != "ok"`
5. **Historical Tracking** - Store artifacts with commit SHA

### Security

1. **Credentials** - Use secrets management (e.g., GitHub Secrets, HashiCorp Vault)
2. **Network** - Isolate services in private networks
3. **TLS** - Use HTTPS for production services
4. **Access Control** - Restrict API tokens

### Scalability

1. **Horizontal Scaling** - Run multiple workers per service
2. **Dataset Management** - Use `COMPARE_LIMIT` for large corpuses
3. **Caching** - Cache oracle ground truth for repeated runs
4. **Parallel Execution** - Run drivers in parallel (future enhancement)

## Support

For issues or questions:
- **GitHub Issues**: https://github.com/LashSesh/infinity-ledger/issues
- **Documentation**: `MEF-Core_v1.0/README_bench.md`
- **Test Suite**: `MEF-Core_v1.0/tests/bench/test_cross_db_integration.py`
