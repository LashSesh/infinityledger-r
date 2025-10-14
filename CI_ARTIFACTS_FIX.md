# CI Artifacts Generation - Complete Fix Summary

## Problem Statement

The CI workflow in `.github/workflows/ci.yml` was failing because the `faiss-api` service referenced at line 136 did not exist in `docker-compose.ci.yml`. This prevented the "Compare HTTP drivers" step from running, which meant only 4 of 6 required compare artifacts could be generated.

## Root Cause

1. **Missing faiss-api service**: The CI workflow expected a `faiss-api` service with `compare-faiss` profile, but it wasn't defined in docker-compose.ci.yml
2. **Dockerfile missing curl**: The healthcheck required curl, but the python:3.11-slim base image doesn't include it
3. **Python 3.12 incompatibility**: faiss-cpu==1.7.4 doesn't support Python 3.12+

## Solution Implemented

### 1. Added faiss-api Service to docker-compose.ci.yml

```yaml
faiss-api:
  build:
    context: ./MEF-Core_v1.0/bench/faiss_http
    dockerfile: Dockerfile
  profiles: ["compare-faiss"]
  environment:
    - FAISS_METRIC=cosine
    - FAISS_INDEX=flat
    - UVICORN_WORKERS=2
  ports:
    - "8090:8090"
  healthcheck:
    test: ["CMD", "curl", "-fsS", "-X", "POST", "http://localhost:8090/clear"]
    interval: 5s
    timeout: 3s
    retries: 30
    start_period: 10s
```

**Why this works:**
- Uses the existing `MEF-Core_v1.0/bench/faiss_http` directory with app.py, Dockerfile, and requirements.txt
- Profile "compare-faiss" matches what CI workflow expects at line 136
- Port 8090 matches FAISS_URL in CI environment variables
- Healthcheck validates service is ready before tests run

### 2. Updated faiss-api Dockerfile

**Key change:** Added curl installation on line 3 for healthcheck support

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV UVICORN_WORKERS=2
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090", "--workers", "2", "--loop", "uvloop"]
```

**Why:** The python:3.11-slim base image doesn't include curl, which is needed for the healthcheck

### 3. Updated faiss-cpu Version Constraint

Changed in `MEF-Core_v1.0/requirements.txt`:
```diff
- faiss-cpu==1.7.4
+ faiss-cpu>=1.7.4
```

**Why:** Python 3.12 requires faiss-cpu >= 1.8.0, so we need a flexible constraint

## CI Workflow Artifact Generation

The CI generates **six compare artifacts** through three distinct stages:

### Stage 1: Docker Compose QA Service
**Location:** Lines 58-73 in `.github/workflows/ci.yml`

**Command:** `python -m tests.bench.compare` (inside qa container)

**Targets:** mef, faiss, qdrant (using src/bench/drivers)

**Artifacts generated:**
- `assets/bench/compare.json`
- `assets/bench/compare.md`

**Validation:** Line 99 checks at least 2 targets have status "ok"

### Stage 2: Compare Pure Drivers
**Location:** Lines 110-122 in `.github/workflows/ci.yml`

**Command:** `python -m pytest -q tests/bench/test_compare.py`

**Targets:** mef-core, faiss-inproc (using tests/bench/compare/drivers)

**Environment:** COMPARE_LIMIT=128, COMPARE_K=10, ANN_METRIC=cosine

**Artifacts generated:**
- `assets/bench/compare_pure.json` (copy of compare.json)
- `assets/bench/compare_pure.md` (copy of compare.md)

### Stage 3: Compare HTTP Drivers
**Location:** Lines 123-142 in `.github/workflows/ci.yml`

**Command:** `python -m pytest -q tests/bench/test_compare.py`

**Targets:** mef-http, faiss-http (using tests/bench/compare/drivers)

**Services started:**
- api (MEF HTTP API on port 8080)
- faiss-api (FAISS HTTP service on port 8090)

**Environment:** MEF_BASE_URL=http://localhost:8080, FAISS_URL=http://localhost:8090

**Artifacts generated:**
- `assets/bench/compare_http.json` (copy of compare.json)
- `assets/bench/compare_http.md` (copy of compare.md)

## Verification

Created comprehensive test suite in `tests/bench/test_ci_artifacts_complete.py`:

- [x] Validates faiss-api service definition  
- [x] Checks compare-faiss profile exists  
- [x] Verifies bench/faiss_http structure  
- [x] Confirms Dockerfile has curl  
- [x] Tests all required drivers registered  
- [x] Validates faiss-cpu version flexibility  
- [x] Verifies docker-compose.ci.yml is valid  

Run with: `python -m pytest tests/bench/test_ci_artifacts_complete.py -v`

## Files Changed

1. **docker-compose.ci.yml** - Added faiss-api service with compare-faiss profile
2. **MEF-Core_v1.0/bench/faiss_http/Dockerfile** - Added curl installation
3. **MEF-Core_v1.0/requirements.txt** - Updated faiss-cpu version constraint
4. **MEF-Core_v1.0/tests/bench/test_ci_artifacts_complete.py** - New comprehensive test

## Expected Behavior

### Before Fix
- CI failed at "Compare HTTP drivers" step (lines 123-142)
- Only 4 artifacts generated (compare.json/md, compare_pure.json/md)
- Missing compare_http.json and compare_http.md
- Upload artifact step failed: "No files were found with the provided path"

### After Fix
- All three compare stages complete successfully
- All 6 artifacts generated:
  - compare.json, compare.md (from docker compose)
  - compare_pure.json, compare_pure.md (from pure drivers)
  - compare_http.json, compare_http.md (from HTTP drivers)
- CI passes all validation checks
- Artifacts uploaded successfully

## Testing Locally

**Note:** All commands assume you are in the repository root directory (where `docker-compose.ci.yml` is located)

### Test faiss-api service:
```bash
# From repository root
docker compose -f docker-compose.ci.yml --profile compare-faiss build faiss-api
docker compose -f docker-compose.ci.yml --profile compare-faiss up -d faiss-api
curl -fsS -X POST http://localhost:8090/clear
docker compose -f docker-compose.ci.yml stop faiss-api
```

### Test pure drivers:
```bash
# From repository root
cd MEF-Core_v1.0
BENCH_COMPARE=1 TARGETS=mef-core,faiss-inproc COMPARE_LIMIT=32 \
  python -m pytest -q tests/bench/test_compare.py
```

### Test HTTP drivers:
```bash
# From repository root
docker compose -f docker-compose.ci.yml --profile compare up -d api
docker compose -f docker-compose.ci.yml --profile compare-faiss up -d faiss-api

# Wait for services to be healthy, then run tests
cd MEF-Core_v1.0
BENCH_COMPARE=1 TARGETS=mef-http,faiss-http COMPARE_LIMIT=32 \
  MEF_BASE_URL=http://localhost:8080 FAISS_URL=http://localhost:8090 \
  python -m pytest -q tests/bench/test_compare.py
```

## References

- CI Workflow: `.github/workflows/ci.yml`
- Docker Compose: `docker-compose.ci.yml`
- FAISS HTTP Service: `MEF-Core_v1.0/bench/faiss_http/`
- Compare Drivers: `MEF-Core_v1.0/tests/bench/compare/drivers/`
- Documentation: `MEF-Core_v1.0/tests/bench/COMPARE_README.md`
