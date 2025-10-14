# Cross-DB Compare Benchmarks

The compare harness exercises the MEF ANN implementation against FAISS using two
execution modes:

- **PURE / core-to-core** – runs the in-process MEF provider (`mef-core`) versus a
  local FAISS index (`faiss-inproc`).
- **HTTP / transport-to-transport** – compares the MEF HTTP API (`mef-http`) with
  the FastAPI FAISS microservice (`faiss-http`).

Both modes emit artifacts under `assets/bench/`:

- `compare.json` – structured measurements for downstream processing.
- `compare.md` – human-readable summary table.

The runner exits with a non-zero status when `BENCH_COMPARE=1` and fewer than two
targets complete successfully or either artifact is missing.

## Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `BENCH_COMPARE` | Enable the compare harness (`1` to run) | `0` |
| `TARGETS` | Comma-separated driver tokens | `mef-core,faiss-inproc,mef-http,faiss-http` |
| `COMPARE_LIMIT` | Max corpus/query size (0 = unlimited) | `500` |
| `COMPARE_K` | Top-k recall / search depth | `10` |
| `UPSERT_BATCH` | Batch size for bulk ingestion | `1000` |
| `ANN_METRIC` | Shared ANN metric (`cosine` or `l2`) | `cosine` |
| `HNSW_M` | HNSW graph degree for MEF/core drivers | `32` |
| `HNSW_EFSEARCH` | HNSW efSearch for MEF/core drivers | `64` |
| `FAISS_INDEX` | FAISS index type (`hnsw` or `flat`) | `hnsw` |
| `FAISS_HNSW_M` | HNSW degree for FAISS drivers | `32` |
| `FAISS_EFSEARCH` | HNSW efSearch for FAISS drivers | `64` |
| `HTTPX_TIMEOUT` | HTTP client timeout (seconds) | `30.0` |
| `MEF_BASE_URL` | Base URL for the MEF API | `http://api:8080` |
| `FAISS_URL` | Base URL for the FAISS HTTP service | `http://faiss-api:8090` |

## Running locally

```bash
# Pure mode (no Docker services required)
BENCH_COMPARE=1 TARGETS=mef-core,faiss-inproc COMPARE_LIMIT=128 \
  python -m pytest -q tests/bench/test_compare.py

# HTTP mode – start the services first
docker compose -f docker-compose.ci.yml --profile compare-faiss up -d faiss-api
BENCH_COMPARE=1 TARGETS=mef-http,faiss-http COMPARE_LIMIT=128 \
  MEF_BASE_URL=http://localhost:8080 FAISS_URL=http://localhost:8090 \
  python -m pytest -q tests/bench/test_compare.py
```

Ensure the MEF API runs with multiple workers (`UVICORN_WORKERS=2`) and keep-alive
enabled when comparing HTTP transports.  The FAISS microservice reads the same
ANN parameter environment variables so both sides share identical index
settings.

## CI integration

- The **pure** step runs the compare runner directly with `TARGETS=mef-core,faiss-inproc`.
- The **HTTP** step brings up the FAISS microservice via the `compare-faiss`
  profile and compares `mef-http` vs `faiss-http`.
- Both steps upload `assets/bench/compare.json` and `compare.md` and fail if the
  artifacts are missing or fewer than two targets finished successfully.
