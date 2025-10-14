# MEF Benchmark Compare Runner

The compare harness extends the existing MEF bench so you can measure MEF and
external vector stores on the exact same dataset, embeddings, queries, metric,
and `k`.

## Prerequisites

* Python 3.11 with the dependencies from `requirements.txt`
* Optional client SDKs depending on which targets you plan to exercise:
  * `qdrant-client`
  * `pymilvus`
  * `weaviate-client`
  * `pinecone-client`
  * Access to running services (see environment variables below)
* Ensure your `PYTHONPATH` includes the repository `src/` directory before
  running the compare harness, for example:

  ```bash
  export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
  ```

## Environment Variables

| Variable | Description |
| --- | --- |
| `BENCH_COMPARE` | Controls whether the compare runner executes. Defaults to `auto` (enabled). Set to `0`/`false`/`off` to skip or `1` to force the compare step and require at least two successful targets. |
| `TARGETS` | Comma-separated list of drivers to run. Defaults to `mef,faiss` unless `BENCH_COMPARE=1`, which promotes the default to `mef,faiss,qdrant,milvus`. |
| `REQUIRED_TARGETS` | Optional comma-separated list of target slugs that must complete successfully. Missing or failing targets raise a non-zero exit code when compare is enabled. |
| `COMPARE_LIMIT` | Limits the dataset size (points and queries) processed by the compare harness, keeping CI-friendly workloads small. |
| `MEF_BASE_URL` | Base URL for the MEF API (defaults to `http://localhost:8080`) |
| `QDRANT_URL` | Base URL for Qdrant |
| `MILVUS_HOST` / `MILVUS_PORT` | Connection parameters for Milvus |
| `WEAVIATE_URL` | Base URL for Weaviate |
| `ELASTIC_URL` | Base URL for Elasticsearch/OpenSearch |
| `PINECONE_API_KEY`, `PINECONE_ENV` | Pinecone credentials |
| `UPSERT_BATCH` | Batch size for ingestion (defaults to 1000) |
| `BENCH_POINTS`, `BENCH_Q`, `BENCH_K` | Dataset sizing knobs |

Only drivers with the required environment variables (and reachable services)
will run; others are reported as skipped with a reason.

## Local Usage

### MEF only

```bash
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
export MEF_BASE_URL=http://localhost:8080
export TARGETS=mef
export BENCH_COMPARE=true
python -m tests.bench.compare
```

### MEF + external services

Start any external services you need (see `docker-compose.ci.yml` for the
Qdrant profile used in CI) and then run:

```bash
export PYTHONPATH="$(pwd)/src:${PYTHONPATH:-}"
export MEF_BASE_URL=http://api:8080
export QDRANT_URL=http://qdrant:6333
export MILVUS_HOST=milvus
export MILVUS_PORT=19530
export TARGETS=mef,faiss,qdrant,milvus
export BENCH_COMPARE=true
python -m tests.bench.compare
```

The command writes two artefacts:

* `assets/bench/compare.json`
* `assets/bench/compare.md`

Both files are always created. Each target is reported with a status (`ok`,
`completed-with-errors`, `skipped`) and, if skipped, a human-readable reason
(e.g. missing environment variables). The Markdown report also contains the
commit hash, dataset summary, latency/recall tables, and an at-a-glance
overview listing every target with its status and reason.

## Running in GitHub Actions

The repository CI workflow now enforces a cross-database compare run by
default. The `build-test` job launches Docker Compose with the `compare`
profile, which starts MEF, the QA container, Qdrant, and Milvus sidecars. The
following environment variables are exported in the workflow so the compare
runner executes deterministically:

```
BENCH_COMPARE=1
TARGETS=mef,faiss,qdrant,milvus
COMPARE_LIMIT=500
REQUIRED_TARGETS=mef,faiss,qdrant
QDRANT_URL=http://qdrant:6333
MILVUS_HOST=milvus
MILVUS_PORT=19530
```

The QA container writes `assets/bench/compare.json` and `assets/bench/compare.md` which are uploaded as artifacts.

### CI/CD Enhancements

The CI pipeline includes enterprise-ready features:

- **Retry Logic**: Automatic retries with exponential backoff for flaky tests
- **Health Verification**: Comprehensive health checks before running benchmarks
- **Error Handling**: Detailed logs and diagnostics on failure
- **Network Segmentation**: Isolated networks for security
- **Resource Limits**: CPU and memory constraints for stability
- **Monitoring**: Optional Prometheus/Grafana integration

See [INFRASTRUCTURE.md](../INFRASTRUCTURE.md) for complete CI/CD documentation.
`assets/bench/compare.md`. CI fails when either artefact is missing or when
fewer than two targets complete successfully. Failures for individual targets
are still recorded in the reports so you can diagnose them from the uploaded
artefacts even if the overall run fails.

To override the target list locally or in a one-off CI run, set
`TARGETS=mef,faiss,qdrant,weaviate` (for example) and optionally extend
`REQUIRED_TARGETS` to ensure specific drivers must pass. Providing
`BENCH_COMPARE=0` or a similar disabled token continues to bypass the compare
step entirely.

## Changelog

- Compare runner now defaults to `mef,faiss`, always emits JSON/Markdown
  reports, and annotates each target with a status/reason so CI artefacts are
  stable even when external services are missing.

## Determinism

* Spiral dataset generation is deterministic and shared with the existing
  bench harness.
* The FAISS baseline driver normalises vectors for cosine/IP metrics to produce
  a deterministic ground-truth ordering for recall.
* Each driver normalises vectors consistently to keep comparisons fair.

## Adding New Drivers

1. Implement `bench.drivers.<your_driver>` inheriting from
   `VectorStoreDriver`.
2. Handle optional dependencies and missing services by raising
   `DriverUnavailable` with a descriptive reason.
3. Register the driver in `bench.drivers.DRIVER_REGISTRY` so the compare
   runner can instantiate it from the `TARGETS` environment variable.
4. Add a smoke test to `tests/bench/test_drivers.py` if appropriate.

## Cross-DB Compare in CI

* The CI job runs `BENCH_COMPARE=1` with `TARGETS=mef,faiss,qdrant,milvus` and a
  `COMPARE_LIMIT` of 500 points/queries so the suite finishes quickly.
* At least two targets must report `status == "ok"`; otherwise the job exits
  with code `2` and surfaces a clear error message both in stderr and in the
  JSON payload.
* You can require additional drivers (for example `REQUIRED_TARGETS=mef,qdrant`
  for smoke coverage) to hard-fail if any of them skips or errors out.
* The runner always produces `assets/bench/compare.json` and
  `assets/bench/compare.md`. Missing or empty artefacts now cause CI to fail so
  cross-database coverage cannot silently disappear.
