# CI Pipeline Robustness Improvements

## Overview

This document describes the comprehensive improvements made to the CI pipeline configuration to ensure robust, production-ready cross-database benchmarking with stable connections, appropriate resource limits, strong health checks, and reliable service verification.

## Changes Made

### 1. Resource Limits Optimization for CI Runners

**Problem**: Milvus service was configured with 4.0 CPU cores, exceeding typical CI runner constraints.

**Solution**: Adjusted all service resource limits to ensure CPU ≤ 2.0 cores per service.

#### Updated Limits in docker-compose.ci.yml

```yaml
# API Service
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: "2G"
    reservations:
      cpus: "0.5"
      memory: "512M"

# Qdrant Service  
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: "2G"
    reservations:
      cpus: "0.5"
      memory: "512M"

# Milvus Service (reduced from 4.0 to 2.0 CPU)
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: "3G"
    reservations:
      cpus: "0.5"
      memory: "512M"

# QA Container
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: "4G"
    reservations:
      cpus: "1.0"
      memory: "1G"
```

**Benefits**:
- Fits within standard GitHub Actions runner constraints (2-core machines)
- Prevents resource exhaustion and OOM kills
- Ensures reproducible performance across CI runs
- Maintains performance for Milvus by increasing retries and start_period

### 2. Enhanced Health Check Configurations

**Problem**: Health checks had varying intervals and timeouts that weren't optimized for reliability.

**Solution**: Standardized and enhanced health check configurations with robust retry logic.

#### API Service Health Check

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"]
  interval: 3s      # Check every 3 seconds (was 5s)
  timeout: 5s       # Wait up to 5s for response (was 3s)
  retries: 60       # Up to 60 retries
  start_period: 30s # Wait 30s before starting checks (was 60s)
```

- **Improvement**: Faster checking (3s vs 5s) with longer timeout (5s vs 3s) for more reliable detection
- **Total wait time**: Up to 3 minutes (60 × 3s) for service to become healthy

#### Qdrant Service Health Check

```yaml
healthcheck:
  test: ["CMD", "bash", "-c", "timeout 2 bash -c '</dev/tcp/localhost/6333' 2>/dev/null"]
  interval: 2s      # Check every 2 seconds
  timeout: 5s       # Wait up to 5s for response (was 3s)
  retries: 90       # Up to 90 retries
  start_period: 20s # Wait 20s before starting checks (was 10s)
```

- **Improvement**: Longer timeout (5s vs 3s) and more generous start_period (20s vs 10s)
- **Total wait time**: Up to 3 minutes (90 × 2s) for service to become healthy

#### Milvus Service Health Check

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:9091/healthz"]
  interval: 3s       # Check every 3 seconds (was 5s)
  timeout: 5s        # Wait up to 5s for response (was 3s)
  retries: 80        # Up to 80 retries (was 60)
  start_period: 90s  # Wait 90s before starting checks (was 60s)
```

- **Improvement**: Faster checking (3s vs 5s), longer timeout (5s vs 3s), more retries (80 vs 60)
- **Total wait time**: Up to 4 minutes (80 × 3s) for service to become healthy
- **Rationale**: Milvus standalone mode needs more time to initialize etcd and storage

### 3. Enhanced Retry Logic in CI Workflow

**Problem**: Retry logic was basic with limited attempts and no detailed logging.

**Solution**: Implemented enhanced retry function with exponential backoff and comprehensive logging.

#### New Retry Function

```bash
retry_with_backoff() {
  local max_attempts=5        # Increased from 3
  local timeout=2             # Start at 2 seconds
  local attempt=1
  local cmd="$@"
  
  while [ $attempt -le $max_attempts ]
  do
    echo "Attempt $attempt/$max_attempts: $cmd"
    if $cmd; then
      echo "✓ Command succeeded on attempt $attempt"
      return 0
    fi
    
    if [ $attempt -eq $max_attempts ]; then
      echo "✗ Command failed after $max_attempts attempts: $cmd"
      return 1
    fi
    
    echo "⚠ Attempt $attempt failed. Waiting ${timeout}s before retry..."
    sleep $timeout
    attempt=$((attempt + 1))
    timeout=$((timeout * 2))  # Exponential backoff: 2, 4, 8, 16, 32
  done
}
```

**Benefits**:
- **Exponential backoff**: 2s → 4s → 8s → 16s → 32s (reduces load on services)
- **More attempts**: 5 attempts (was 3)
- **Better logging**: Shows attempt number and provides clear success/failure messages
- **Total retry time**: Up to ~60 seconds (2+4+8+16+32)

### 4. Post-Benchmark Service Verification

**Problem**: No verification that services remained healthy after benchmark execution.

**Solution**: Added comprehensive post-benchmark verification step to CI workflow.

#### Implementation

```yaml
- name: Verify services still healthy (post-benchmark)
  if: always()
  run: |
    echo "===================================="
    echo "Post-Benchmark Service Verification"
    echo "===================================="
    
    # Check each service is running and endpoints respond
    # - API: http://localhost:8080/healthz
    # - Qdrant: http://localhost:6333/readyz
    # - Milvus: http://localhost:9091/healthz
    
    # Report summary
    echo "Services online and accessible: $services_running/3"
```

**What It Checks**:
1. Container is still running (not crashed/restarted)
2. Health endpoint responds correctly
3. Logs are captured if service failed

**Benefits**:
- Detects services that crash during benchmarking
- Provides diagnostic information for failures
- Confirms infrastructure stability throughout the CI run
- Runs with `if: always()` so executes even if benchmarks fail

### 5. Improved Logging and Diagnostics

**Changes**:

1. **Structured output** with section headers:
   ```
   ====================================
   Starting Docker Services
   ====================================
   ```

2. **Timestamps** in wait loops:
   ```
   [10:23:45] Waiting for milvus...
   ```

3. **Status indicators**:
   - ✓ Success messages
   - ✗ Error messages  
   - ⚠ Warning messages

4. **Context in errors**:
   - Last 50 lines of logs on failure
   - Container status output
   - Clear indication of which service failed

5. **Progress visibility**:
   - Shows retry attempts: "Attempt 1/5"
   - Shows wait times: "Waiting ${timeout}s before retry..."
   - Shows elapsed time for service readiness

## Verification and Testing

### Added Tests

Four new test functions in `test_ci_service_health.py`:

1. **`test_ci_resource_limits_for_runners()`**
   - Validates all services have CPU ≤ 2.0
   - Parses docker-compose environment variable defaults
   - Ensures CI runner compatibility

2. **`test_health_check_retry_parameters()`**
   - Validates health check intervals, timeouts, and retries
   - Ensures API: 3s interval, 5s timeout, 60+ retries
   - Ensures Qdrant: 2s interval, 5s timeout, 90+ retries
   - Ensures Milvus: 3s interval, 5s timeout, 80+ retries

3. **`test_ci_post_benchmark_verification()`**
   - Validates CI workflow has post-benchmark verification step
   - Checks all three services are verified (API, Qdrant, Milvus)
   - Confirms summary reporting is present

4. **`test_ci_enhanced_retry_logic()`**
   - Validates enhanced retry function exists
   - Confirms exponential backoff implementation
   - Checks for improved logging with attempt numbers

### Test Results

```
============ 12 passed in 0.17s ============
✓ test_docker_compose_health_checks
✓ test_qa_service_dependencies
✓ test_qa_service_dependency_verification
✓ test_ci_workflow_service_verification
✓ test_ci_workflow_output_validation
✓ test_pymilvus_in_requirements
✓ test_ci_workflow_timeout_values
✓ test_docker_compose_milvus_configuration
✓ test_ci_resource_limits_for_runners (NEW)
✓ test_health_check_retry_parameters (NEW)
✓ test_ci_post_benchmark_verification (NEW)
✓ test_ci_enhanced_retry_logic (NEW)
```

## Configuration Validation

### Docker Compose Validation

```bash
$ docker compose -f docker-compose.ci.yml --profile compare config >/dev/null
✓ docker-compose.ci.yml is valid
```

### Resource Limits Verification

```bash
$ docker compose -f docker-compose.ci.yml --profile compare config | grep -A 3 "cpus:"

# Output (processed from environment variables):
api: cpus: "2"
qdrant: cpus: "2"
milvus: cpus: "2" (reduced from 4)
qa: cpus: "2"
```

All services now have CPU ≤ 2.0 ✓

### Health Check Verification

```bash
$ docker compose -f docker-compose.ci.yml --profile compare config | grep -A 5 "healthcheck:"

# Output:
# API: interval=3s, timeout=5s, retries=60, start_period=30s
# Qdrant: interval=2s, timeout=5s, retries=90, start_period=20s
# Milvus: interval=3s, timeout=5s, retries=80, start_period=90s
```

All health checks have robust retry parameters ✓

## Expected Behavior

### Service Startup Sequence

1. **Start services** (with retry):
   ```
   Attempt 1/5: docker compose up -d api qdrant milvus
   ✓ Command succeeded on attempt 1
   ```

2. **Wait for API** (up to 120s):
   ```
   Waiting for API service to be healthy...
   [10:23:10] Waiting for api...
   [10:23:12] Waiting for api...
   ✓ API service is healthy
   ```

3. **Wait for Qdrant** (up to 120s):
   ```
   Waiting for Qdrant service to be healthy...
   [10:23:15] Waiting for qdrant...
   ✓ Qdrant service is healthy
   ```

4. **Wait for Milvus** (up to 180s):
   ```
   Waiting for Milvus service to be healthy (this may take up to 3 minutes)...
   [10:23:20] Waiting for milvus...
   [10:23:23] Waiting for milvus...
   [10:24:15] Waiting for milvus...
   ✓ Milvus service is healthy
   ```

5. **Verify endpoints** (with retry):
   ```
   Verifying API endpoint...
   Attempt 1/5: curl -fsS http://localhost:8080/healthz
   ✓ Command succeeded on attempt 1
   ✓ API endpoint verified
   
   [Same for Qdrant and Milvus]
   ```

6. **Run benchmarks**:
   ```
   QA container executes benchmark suite
   ```

7. **Post-benchmark verification**:
   ```
   ====================================
   Post-Benchmark Service Verification
   ====================================
   
   ✓ API container is running
   ✓ API health endpoint responding
   
   ✓ Qdrant container is running
   ✓ Qdrant readyz endpoint responding
   
   ✓ Milvus container is running
   ✓ Milvus healthz endpoint responding
   
   ====================================
   Service Verification Summary
   ====================================
   Services online and accessible: 3/3
   
   ✓ SUCCESS: All services remain healthy after benchmarking
   ```

### Failure Scenarios

#### Service Fails to Start

```
✗ ERROR: Milvus service failed to become healthy within 180s

Milvus service logs (last 50 lines):
[logs here]

Container status:
NAME     STATUS
milvus   starting

[CI run fails with exit code 1]
```

#### Endpoint Not Responding

```
Attempt 1/5: curl -fsS http://localhost:9091/healthz
⚠ Attempt 1 failed. Waiting 2s before retry...
Attempt 2/5: curl -fsS http://localhost:9091/healthz
✓ Command succeeded on attempt 2
```

#### Service Crashes During Benchmarks

```
====================================
Post-Benchmark Service Verification
====================================

✓ API container is running
✓ API health endpoint responding

✗ Milvus container not running

[Diagnostic logs captured]

Services online and accessible: 2/3

⚠ WARNING: Not all services are accessible
```

## Benefits Summary

### Stability
- **Resource limits**: Prevents OOM and resource exhaustion
- **Health checks**: Ensures services are truly ready before use
- **Post-verification**: Confirms services survived the benchmark run

### Reliability
- **Exponential backoff**: Reduces load on struggling services
- **More retries**: Accommodates slower CI runners
- **Longer timeouts**: Handles network delays and slow starts

### Reproducibility
- **Fixed resource limits**: Consistent performance across runs
- **Deterministic waits**: No race conditions in startup
- **Clear logging**: Easy to diagnose issues

### Maintainability
- **Comprehensive tests**: Validates configuration correctness
- **Clear documentation**: Easy to understand and modify
- **Structured logging**: Quick debugging of failures

## Environment Variables

Updated in `.env.example`:

```bash
# Resource limits optimized for CI runners
MILVUS_CPU_LIMIT=2.0         # Reduced from 4.0
MILVUS_MEMORY_LIMIT=3G       # Reduced from 4G
MILVUS_MEMORY_RESERVATION=512M  # Optimized for CI
```

## Compatibility

- ✓ GitHub Actions (ubuntu-24.04)
- ✓ Self-hosted runners with 2+ cores
- ✓ Local development (docker-compose)
- ✓ Production deployments (see docker-compose.production.yml)

## Migration Notes

No migration required. Changes are backward compatible:

1. Resource limits use environment variables with sensible defaults
2. Health checks are internal to docker-compose
3. CI workflow changes are additive (new verification step)
4. Existing tests continue to pass

## Future Improvements

Potential enhancements for consideration:

1. **Dynamic resource allocation** based on runner capabilities
2. **Parallel service startup** where dependencies allow
3. **Health check metrics** exported to monitoring
4. **Service dependency graph** visualization
5. **Automated rollback** on service failure
6. **Network policy enforcement** for service isolation

## References

- Docker Compose health check docs: https://docs.docker.com/compose/compose-file/05-services/#healthcheck
- GitHub Actions runner specs: https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners
- Milvus standalone mode: https://milvus.io/docs/install_standalone-docker.md
- Qdrant health checks: https://qdrant.tech/documentation/guides/administration/
