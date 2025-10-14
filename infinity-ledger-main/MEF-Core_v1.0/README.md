# MEF-Core: Mandorla Eigenstate Fractals Core System

[![CI/CD](https://github.com/mef-core/mef-core/workflows/MEF-Core%20CI/CD%20Pipeline/badge.svg)](https://github.com/mef-core/mef-core/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/docker/v/mef-core/mef-core)](https://hub.docker.com/r/mef-core/mef-core)

## Overview

MEF-Core is a deterministic, domain-agnostic information transformation pipeline that implements post-symbolic processing through geometric and resonance-based structures. The system transforms arbitrary raw information through a series of mathematical operations, ultimately producing immutable audit trails of information evolution.

### Key Features

- **Deterministic Processing**: Identical inputs with identical seeds always produce identical outputs
- **Domain-Agnostic**: Works with any data type (text, JSON, numeric, binary)
- **5D Spiral Storage**: Novel geometric embedding in five-dimensional space
- **Contractive Operators**: Guaranteed convergence to stable fixpoints
- **Temporal Information Crystals**: Crystalline attractors that stabilize information
- **Immutable Ledger**: Hash-chained blocks with cryptographic integrity
- **Path Invariance**: Hyperdimensional DAG ensuring reproducible transformations
- **Proof-of-Resonance**: Mathematical validation of information stability
- **Xswap Alignment**: HDAG-backed manifold alignment with Merkaba-Gate proof
  and ledger audit for cross-domain similarity

## Architecture

```
Acquisition → Ingestion/Triton → Spiral-5D → Solve–Coagula → TIC → MEF-Ledger → HDAG → API/CLI
```

### Components

1. **Trident Core**: Normalization layer for heterogeneous data ingestion
2. **Spiral Storage**: 5D geometric embedding with phase-based addressing
3. **Solve–Coagula**: Contractive operator stack (DoubleKick, Sweep, Pfadinvarianz, Weight-Transfer)
4. **TIC Crystallizer**: Temporal Information Crystal materialization
5. **MEF Ledger**: Immutable hash-chained block storage
6. **HDAG**: Hyperdimensional Directed Acyclic Graph for path invariance
7. **API/CLI**: RESTful API and command-line interface

## Installation

### Using pip

```bash
pip install mef-core
```

### From source

```bash
git clone https://github.com/mef-core/mef-core.git
cd mef-core
pip install -r requirements.txt
pip install -e .
```

### Using Docker

```bash
docker pull mef-core/mef-core:latest
docker run -p 8000:8000 -v /path/to/data:/app/data mef-core/mef-core
```

## Enterprise Deployment

MEF-Core includes production-ready infrastructure for enterprise deployments with comprehensive monitoring, security, and scalability features.

### Quick Start - Production Deployment

```bash
# 1. Copy and configure environment
cp .env.production .env
# Edit .env with your credentials

# 2. Set up Docker secrets (recommended)
echo "your-api-token" | docker secret create mef_api_token -
echo "your-quality-token" | docker secret create quality_token -

# 3. Deploy with monitoring
docker compose -f docker-compose.production.yml \
  --profile production \
  --profile monitoring \
  up -d

# 4. Verify deployment
docker compose -f docker-compose.production.yml ps
curl http://localhost:8080/healthz

# 5. Access monitoring
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

### Key Enterprise Features

- **Network Segmentation**: Isolated networks for test, database, and monitoring traffic
- **Resource Management**: CPU and memory limits for all services
- **Health Checks**: Comprehensive health monitoring with automatic restarts
- **Centralized Logging**: JSON-structured logs with rotation and retention policies
- **Monitoring Stack**: Prometheus metrics + Grafana dashboards
- **Secrets Management**: Support for Docker Secrets, Vault, AWS Secrets Manager
- **High Availability**: Restart policies and health checks for automatic recovery
- **Environment Profiles**: Pre-configured for development, staging, and production

### Documentation

- **[INFRASTRUCTURE.md](../INFRASTRUCTURE.md)**: Complete infrastructure documentation
- **[SECRETS_MANAGEMENT.md](../SECRETS_MANAGEMENT.md)**: Secrets and credentials management
- **[README_bench.md](README_bench.md)**: Benchmark and testing documentation

### Environment Configuration

Three environment templates are provided:

```bash
# Development (lightweight, no auth)
docker compose --env-file .env.development up

# Staging (production-like, with auth)
docker compose --env-file .env.staging up

# Production (full resources, monitoring)
docker compose -f docker-compose.production.yml \
  --env-file .env.production \
  --profile production --profile monitoring up -d
```

## Quick Start

### Python API

```python
from mef_core import MEFCore

# Initialize with seed
mef = MEFCore(seed="MEF_SEED_42")

# Process data through complete pipeline
result = mef.process({
    "data": "Your input data here",
    "type": "text"
})

print(f"Snapshot ID: {result['snapshot_id']}")
print(f"TIC ID: {result['tic_id']}")
print(f"Block Index: {result['block_index']}")
```

## Xswap Cross-Domain Alignment

Xswap extends the domain layer with HDAG-assisted manifold alignment between
heterogeneous payloads. The orchestrator processes each payload through the
DomainLayer, aligns the resulting meshes in Metatron space, verifies the result
via the Merkaba-Gate decision logic, updates the HDAG, and—when the gate is
passed—commits an audit block to the MEF ledger.

```python
from pathlib import Path

from src.domains.domain_layer import DomainLayer
from src.domains.xswap import Xswap
from src.gates.merkaba_gate import MerkabaGate
from src.hdag.graph import HDAG
from src.ledger.mef_block import MEFLedger
from src.mef_core_pipeline import MEFCorePipeline

pipeline = MEFCorePipeline(storage_path="./store", ledger_path="./ledger")
domain_layer = DomainLayer(pipeline, pipeline.metatron_router, storage_path="./domains")

xswap = Xswap(
    domain_layer=domain_layer,
    merkaba_gate=MerkabaGate(),
    hdag=HDAG("./hdag"),
    ledger=MEFLedger("./ledger"),
    audit_path=Path("logs/xswap.jsonl"),
)

artifacts = xswap.align(
    source_payload="Merkaba resonance activates coherent transfer.",
    target_payload=[0.2, 0.4, 0.8, 0.1],
    source_domain="text",
    target_domain="signal",
)

print(artifacts.alignment_score, artifacts.gate_event["decision"])
```

The audit artefacts (Merkaba proof, HDAG nodes/edges, ledger block metadata)
are appended to ``logs/xswap.jsonl`` for downstream inspection.

### Command Line

```bash
# Start API server
mef-server

# Ingest a file
mef ingest data.txt --type text --seed MEF_SEED_42

# Process snapshot
mef process <snapshot_id> --commit

# Audit ledger
mef audit --export

# Check system status
mef status --detailed
```

### REST API

```bash
# Health check
curl http://localhost:8000/ping

# Ingest data
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"data": "test data", "data_type": "text", "seed": "MEF_SEED_42"}'

# Process snapshot
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{"snapshot_id": "...", "auto_commit": true}'

# Vector search (ANN fast path)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
        "collection": "spiral",
        "query_vector": [0.1, 0.2, 0.3, 0.4, 0.5],
        "top_k": 5,
        "mode": "ann",
        "membership_proof": true,
        "pipeline_proof": true
      }'

# Override the index provider for a single search (read-only)
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
        "collection": "spiral",
        "query_vector": [0.1, 0.2, 0.3, 0.4, 0.5],
        "top_k": 5,
        "mode": "ann",
        "provider": "ivf_pq"
      }'

# Update the default provider (admin operation)
curl -X PATCH http://localhost:8000/collections/spiral/provider \
  -H "Authorization: Bearer ${QUALITY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"provider": "ivf_pq"}'

# Get ledger block
curl http://localhost:8000/ledger/0
```

#### Provider semantics

- `provider` in the `/search` payload is a **per-request hint**. The override is satisfied by an ephemeral index instance; it never mutates the persisted provider configuration.
- Every search response sets the header `X-Provider-Used: <name>@<version>` to document the effective backend. The same metadata is mirrored in `/debug/search-plan` under `provider_used`.
- The default provider for a collection can be changed via `PATCH /collections/{name}/provider`. This admin-only call bumps the collection's `proof_version`, persists the new configuration, and marks the index as not ready until a rebuild completes.
- Proof-carrying retrieval reuses the existing `proof_version` for read-only overrides, so membership and pipeline proofs remain valid across provider hints.

## Configuration

Create a `config.yaml` file:

```yaml
seed: "MEF_SEED_42"

spiral:
  r: 1.0
  a: 0.05
  b: 0.2
  c: 0.2
  k: 2
  step: 0.01

solvecoagula:
  lambda: 0.8
  eps: 1.0e-6
  max_iter: 1000

operators:
  dk:
    alpha1: 0.05
    alpha2: -0.03
  sw:
    tau0: 0.5
    beta: 0.1
    schedule: "cosine"
  pi:
    canon: "lexicographic"
    tol: 1.0e-6
  wt:
    gamma: 0.1
    levels: ["micro", "meso", "macro"]

gate:
  por_delta: 0.02
  phi_star: 0.6
  mci_min: 0.9

ledger:
  path: "C:/MEF/ledger"

store:
  path: "C:/MEF/store"

vector_store:
  # Local persistence of vector indexes (defaults to <store>/vector_db when omitted)
  path: "C:/MEF/vector_db"
  persistence:
    provider: "s3"
    bucket: "my-mef-vector-bucket"
    prefix: "indexes"
```

### Vector Store Persistence

- ``vector_store.path``: Zielordner für Vektor- und Indexartefakte.
- ``vector_store.persistence``: Optionale Angaben zur Replikation auf S3.
  - ``provider`` muss auf ``s3`` gesetzt werden, damit Uploads aktiviert werden.
  - ``bucket``: Name des Ziel-Buckets.
  - ``prefix``: Optionaler Namespace innerhalb des Buckets.

Sind keine S3-Parameter gesetzt, verbleiben die Artefakte ausschließlich auf dem lokalen Dateisystem.

## Mathematical Foundation

### Spiral Embedding
```
s(θ) = (r cos θ, r sin θ, aθ, b sin(kθ), c cos(kθ))
```

### Solve–Coagula Convergence
```
v_{t+1} = λ(Wv_t + b), 0 < λ < 1
```

### Proof-of-Resonance
```
FFT(s) → ŝ; r' = g(ŝ) ∈ [0,1]
Acceptance: |r' - r_snapshot| ≤ δ ∧ λ_gap ≥ λ_min
```

## Testing

### Unit Tests
```bash
pytest tests/
```

### E2E Determinism Tests
```bash
pytest tests/test_e2e.py::TestDeterminism -v
```

### Performance Benchmarks
```bash
pytest tests/test_benchmark.py --benchmark-only
```

Benchmark runs honour the configuration stored in `assets/bench/bench_config.json`.
Timeouts and retry parameters can be adjusted there without touching the test
code. The default profile increases the HTTP connect/read timeouts to 30s/60s
with a dedicated 120s budget for bulk operations and enables exponential
backoff (5 attempts, factor 2). Batch ingestion automatically adapts between
500 and 5,000 vectors based on observed latencies, resuming from the
`assets/bench/checkpoint.json` file if a run is interrupted.

### Golden Snapshot Controls

The golden property test honours several environment variables so CI can stabilise
long-running snapshot builds without affecting local safety defaults:

| Variable | Default | Description |
| --- | --- | --- |
| `GOLDEN_DATASET_COUNT` | `30` | Number of base samples written to `dataset.jsonl`. |
| `GOLDEN_COUNT` | `30` | Target number of successful golden runs to attempt. |
| `GOLDEN_MIN_OK` | `30` | Minimum confirmed runs required for the test to pass. |
| `GOLDEN_ATTEMPTS_PER_SAMPLE` | `10` | Maximum retries per dataset entry before moving on. |
| `GOLDEN_ATTEMPTS_FACTOR` | `5` | Global retry budget multiplier (`len(dataset) * factor`). |
| `GOLDEN_RELAX_POR` | `0` | Set to `1` to immediately retry PoR holds with a CI override header. |
| `GOLDEN_HOLD_POLICY` | `` | When set to `skip`, CI will skip instead of failing if PoR holds exhaust the retry budget. |

The strictness flag (`GOLDEN_STRICT`) still forces an exact `GOLDEN_COUNT` match
when set to `1`. CI pipelines in this repository pin `GOLDEN_MIN_OK=10`,
`GOLDEN_ATTEMPTS_FACTOR=8`, and `GOLDEN_HOLD_POLICY=skip` so flaky PoR holds do
not fail the build, while local runs continue to demand the full golden set.

#### Troubleshooting: "NumPy shadowed"

`tests/bench/recall_eval.py` now validates the NumPy import at startup. If you see
an exception similar to `Numpy shadowed: np.__file__=...?`, remove or rename any
local files/directories named `numpy` that might sit on `PYTHONPATH`. The CI
environment pins `PYTHONPATH` to `MEF-Core_v1.0`, `MEF-Core_v1.0/src`, and
`MEF-Core_v1.0/tools` to prevent accidental shadowing and to expose the shared
`bench` package.

## Cloud Deployment

### AWS S3 Integration

```python
from mef_core.storage import S3StorageAdapter

s3_config = {
    'bucket': 'mef-core-storage',
    'region': 'us-east-1',
    'access_key_id': 'YOUR_KEY',
    'secret_access_key': 'YOUR_SECRET'
}

s3_adapter = S3StorageAdapter(s3_config)
s3_adapter.sync_to_s3(local_path, 'snapshot')
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mef-core
spec:
  replicas: 3
  selector:
    matchLabels:
      app: mef-core
  template:
    metadata:
      labels:
        app: mef-core
    spec:
      containers:
      - name: mef-core
        image: mef-core/mef-core:latest
        ports:
        - containerPort: 8000
        env:
        - name: MEF_SEED
          value: "MEF_SEED_42"
        volumeMounts:
        - name: storage
          mountPath: /app/data
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: mef-storage-pvc
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/mef-core/mef-core.git
cd mef-core

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements.txt
pip install -e ".[dev]"

# Run linters
black src/ tests/
flake8 src/ tests/
mypy src/

# Run tests with coverage
pytest --cov=src --cov-report=html
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Documentation

Full documentation is available at [https://mef-core.readthedocs.io](https://mef-core.readthedocs.io)

### API Reference

- [Spiral Module](docs/api/spiral.md)
- [Solve-Coagula Operators](docs/api/solvecoagula.md)
- [TIC Crystallizer](docs/api/tic.md)
- [MEF Ledger](docs/api/ledger.md)
- [HDAG](docs/api/hdag.md)

## Performance

### Benchmarks (Intel i7-10700K, 32GB RAM)

| Operation | Time | Throughput |
|-----------|------|------------|
| Snapshot Creation | 15ms | 66/sec |
| Solve-Coagula Convergence | 200ms | 5/sec |
| TIC Generation | 50ms | 20/sec |
| Ledger Commit | 25ms | 40/sec |
| PoR Validation | 10ms | 100/sec |

## Security

- All operations are deterministic with fixed seeds
- Ledger uses SHA-256 hash chaining
- S3 integration supports server-side encryption
- No external dependencies for core operations
- Regular security audits with Trivy and Bandit

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Citation

If you use MEF-Core in your research, please cite:

```bibtex
@software{mef_core_2025,
  title = {MEF-Core: Mandorla Eigenstate Fractals Core System},
  author = {MEF-Core Project},
  year = {2025},
  url = {https://github.com/mef-core/mef-core},
  version = {1.0.0}
}
```

## Acknowledgments

- Inspired by post-symbolic AI research
- Based on contractive operator theory
- Implements novel 5D spiral topology

## Support

- GitHub Issues: [https://github.com/mef-core/mef-core/issues](https://github.com/mef-core/mef-core/issues)
- Discussion Forum: [https://github.com/mef-core/mef-core/discussions](https://github.com/mef-core/mef-core/discussions)
- Email: mef-core@example.com

## Roadmap

- [ ] v1.1: GPU acceleration for Spiral operations
- [ ] v1.2: Distributed ledger consensus
- [ ] v1.3: Quantum-resistant cryptography
- [ ] v2.0: Multi-dimensional resonance fields
- [ ] v2.1: Adaptive operator learning

---

**MEF-Core** - *Transforming Information Through Mathematical Invariance*
