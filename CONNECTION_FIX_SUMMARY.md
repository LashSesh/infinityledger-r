# Connection Requirements Fix for Qdrant & Milvus

## Problem Statement

The health checks for Qdrant and Milvus were failing in CI not because the services themselves were broken, but because the fundamental connection requirements were not properly established:

1. **Qdrant health check was ineffective**: The health check had a fallback that always passed (`exit 0`) when curl/wget were not available, meaning it could report "healthy" even when the service was not ready
2. **No connection verification**: The QA container would start benchmarks immediately after Docker health checks passed, without verifying actual network connectivity from the container
3. **Insufficient startup time**: Services needed more time to fully initialize before accepting connections

## Root Cause Analysis

### Issue 1: Qdrant Health Check Always Passed

**Problem**: The Qdrant container (qdrant/qdrant:v1.8.3) does not have curl or wget installed. The health check had this logic:

```yaml
test: ["CMD-SHELL", "if command -v curl >/dev/null 2>&1; then curl -fsS http://localhost:6333/readyz; elif command -v wget >/dev/null 2>&1; then wget -qO- http://localhost:6333/readyz; else exit 0; fi"]
```

Since neither curl nor wget were available, it would always execute `exit 0`, making the health check pass immediately regardless of service readiness.

**Impact**: Docker would mark the container as "healthy" even if Qdrant was still starting up or had failed to start properly.

### Issue 2: No Verification of Container-to-Container Connectivity

**Problem**: While Docker's health checks run inside each container, the QA container needs to connect to Qdrant and Milvus over the Docker network. There was no verification that services were reachable from the QA container's network perspective.

**Impact**: Even if Docker marked services as "healthy", they might not be reachable due to network timing issues, DNS resolution delays, or port binding propagation.

### Issue 3: Insufficient Milvus Startup Time

**Problem**: Milvus standalone mode needs significant time to initialize (embedded etcd, storage initialization, etc.). The start_period was only 30s, which might be insufficient.

**Impact**: Health checks could start too early and fail spuriously, or pass before the service was truly ready.

## Solutions Implemented

### Fix 1: Robust Qdrant Health Check Using Bash TCP Test

**Change**: Replaced the curl/wget-based health check with a bash TCP connection test:

```yaml
healthcheck:
  test: ["CMD", "bash", "-c", "timeout 1 bash -c '</dev/tcp/localhost/6333' 2>/dev/null"]
  interval: 2s
  timeout: 3s
  retries: 90
  start_period: 10s
```

**Why this works**:
- Bash is available in the Qdrant container
- `/dev/tcp/host/port` is a bash feature that opens a TCP connection
- Will fail with exit code 1 if the port is not listening
- Provides a true test of service readiness

### Fix 2: Extended Milvus Startup Period

**Change**: Increased Milvus start_period from 30s to 60s:

```yaml
healthcheck:
  test: ["CMD", "curl", "-fsS", "http://localhost:9091/healthz"]
  interval: 5s
  timeout: 3s
  retries: 60
  start_period: 60s  # Increased from 30s
```

**Why this works**:
- Milvus standalone mode needs time to initialize embedded etcd and storage
- start_period allows the container to take longer before health checks count as failures
- Health checks during start_period won't mark the container as unhealthy

### Fix 3: Connection Pre-Check in QA Container

**Change**: Added Phase 0 to QA container startup that verifies network connectivity:

```bash
echo "==== Phase 0: Verify Service Connectivity ===="

# Test API connectivity
while ! curl -fsS "${QUALITY_BASE_URL}/healthz" >/dev/null 2>&1; do
  # wait with timeout
done

# Test Qdrant connectivity  
while ! curl -fsS "${QDRANT_URL}/readyz" >/dev/null 2>&1; do
  # wait with timeout
done

# Test Milvus connectivity (TCP check)
while ! timeout 2 bash -c "cat < /dev/null > /dev/tcp/${MILVUS_HOST}/${MILVUS_PORT}" 2>/dev/null; do
  # wait with timeout
done
```

**Why this works**:
- Runs inside the QA container, testing from the actual client perspective
- Verifies HTTP endpoints for API and Qdrant
- Verifies TCP connectivity for Milvus gRPC port
- Fails fast with clear error messages if services aren't reachable
- Includes timeout to prevent infinite waiting

### Fix 4: Explicit Network Configuration

**Change**: Added explicit network definition:

```yaml
networks:
  default:
    driver: bridge
    name: infinity-ledger-ci
```

**Why this works**:
- Makes the network configuration explicit rather than implicit
- Ensures consistent network naming across runs
- Provides a stable network for container-to-container communication

## Testing the Fixes

### Test 1: Validate Docker Compose Configuration

```bash
docker compose -f docker-compose.ci.yml --profile compare config >/dev/null
echo $?  # Should be 0
```

### Test 2: Start Services and Check Health

```bash
# Clean slate
docker compose -f docker-compose.ci.yml down -v

# Start services
docker compose -f docker-compose.ci.yml --profile compare up -d api qdrant milvus

# Watch health status
watch -n 2 'docker compose -f docker-compose.ci.yml ps'

# Expected: All services should become "healthy" within 2 minutes
```

### Test 3: Verify Connectivity from QA Container

```bash
# After services are healthy, run QA container
docker compose -f docker-compose.ci.yml --profile compare up qa

# Expected output should show:
# - Phase 0: Verify Service Connectivity
# - All three services reported as reachable
# - Then proceed to Phase 1 (Install Dependencies)
```

### Test 4: Full CI Run

```bash
# Run complete benchmark suite
docker compose -f docker-compose.ci.yml --profile compare up --abort-on-container-exit --exit-code-from qa qa

# Expected: 
# - All phases complete successfully
# - compare.json and compare.md generated
# - At least 2 targets succeed (mef, faiss, qdrant, milvus)
```

## Troubleshooting Guide

### Issue: Qdrant health check still failing

**Symptoms**: `docker compose ps` shows qdrant as "unhealthy"

**Diagnosis**:
```bash
# Check if port is listening inside container
docker compose exec qdrant bash -c 'timeout 1 bash -c "</dev/tcp/localhost/6333"'

# Check Qdrant logs
docker compose logs qdrant
```

**Solutions**:
- If port test fails but service is running: Qdrant may still be initializing storage
- If logs show errors: Check for port conflicts or storage permission issues

### Issue: Milvus health check failing

**Symptoms**: Milvus marked as unhealthy after start_period

**Diagnosis**:
```bash
# Check health endpoint from inside container
docker compose exec milvus curl -fsS http://localhost:9091/healthz

# Check Milvus logs
docker compose logs milvus | grep -i error
```

**Solutions**:
- If health endpoint returns non-200: Wait longer, embedded etcd may still be initializing
- If curl fails: Network issue within container - check Milvus logs
- Consider increasing start_period further for slower systems

### Issue: QA container reports service not reachable

**Symptoms**: Phase 0 fails with "service not reachable" error

**Diagnosis**:
```bash
# Check service health from host
curl -fsS http://localhost:6333/readyz  # Qdrant
curl -fsS http://localhost:9091/healthz  # Milvus health
curl -fsS http://localhost:8080/healthz  # API

# Check if services are on same network
docker network inspect infinity-ledger-ci

# Try connection from QA container
docker compose run --rm qa curl -fsS http://qdrant:6333/readyz
```

**Solutions**:
- If host can reach but QA cannot: DNS resolution issue, wait a few seconds
- If neither can reach: Service actually not ready, check service logs
- If DNS fails: Ensure all containers are on infinity-ledger-ci network

### Issue: Connection works but benchmarks fail

**Symptoms**: Phase 0 passes but benchmarks report connection errors

**Diagnosis**:
```bash
# Check if Python drivers can connect
docker compose run --rm qa python -c "
from pymilvus import connections, utility
connections.connect(alias='test', host='milvus', port='19530')
print('Milvus version:', utility.get_server_version())
"

docker compose run --rm qa python -c "
from qdrant_client import QdrantClient
client = QdrantClient(url='http://qdrant:6333')
print('Qdrant health:', client.get_health())
"
```

**Solutions**:
- If Python connection fails: Check driver versions in requirements.txt
- If timeout: Increase BENCH_CONNECT_TIMEOUT environment variable
- If authentication errors: Check credentials configuration

## Future Improvements

1. **Add Qdrant HTTP health check**: Consider installing curl in Qdrant container or using grpc_health_probe
2. **Implement retry with exponential backoff**: Make connection retries more intelligent
3. **Add network latency monitoring**: Log round-trip times during connection checks
4. **Create health check test suite**: Automated tests for health check reliability
5. **Add service dependency graph visualization**: Help developers understand service dependencies

## References

- [Docker Compose Healthcheck Documentation](https://docs.docker.com/compose/compose-file/compose-file-v3/#healthcheck)
- [Qdrant REST API Documentation](https://qdrant.tech/documentation/interfaces/rest/)
- [Milvus Health Check Endpoint](https://milvus.io/docs/monitor.md)
- [Bash /dev/tcp Feature](https://www.gnu.org/software/bash/manual/html_node/Redirections.html)

## Summary

This fix establishes the fundamental connection requirements that were missing:

✅ **Qdrant health check now reliably tests service readiness** (TCP connection test)  
✅ **Milvus has sufficient startup time** (60s start_period)  
✅ **QA container verifies connectivity before benchmarks** (Phase 0 pre-check)  
✅ **Explicit network configuration** ensures consistent DNS resolution  
✅ **Clear error messages** help diagnose connection issues quickly  

The health checks were not broken - the connection foundation was incomplete. Now they have the proper basis to function correctly.
