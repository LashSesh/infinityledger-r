# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the MEF-Core benchmark and testing infrastructure.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [CI/CD Pipeline Issues](#cicd-pipeline-issues)
- [Service Connectivity Issues](#service-connectivity-issues)
- [Connection Requirements for Qdrant & Milvus](#connection-requirements-for-qdrant--milvus)
- [Benchmark Failures](#benchmark-failures)
- [Docker Issues](#docker-issues)
- [Performance Issues](#performance-issues)
- [Data Issues](#data-issues)

---

## Quick Diagnostics

### Run Pre-Flight Check
Before investigating specific issues, run the pre-flight validation:

```bash
cd MEF-Core_v1.0
python tests/bench/preflight_check.py
```

This will validate:
- ✅ All environment variables
- ✅ Python dependencies
- ✅ Directory permissions

### Check Service Health
Test that all services are running and responding:

```bash
# MEF-Core API
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz

# Qdrant
curl -fsS http://localhost:6333/readyz
curl -fsS http://localhost:6333/healthz

# Milvus
curl -fsS http://localhost:9091/healthz

# FAISS HTTP API (if running)
curl -fsS -X POST http://localhost:8090/clear
```

---

## Connection Requirements for Qdrant & Milvus

**If you're experiencing health check failures or connection issues with Qdrant and Milvus**, see the comprehensive guide:

📖 **[CONNECTION_FIX_SUMMARY.md](../CONNECTION_FIX_SUMMARY.md)**

This covers:
- Root cause analysis of health check failures
- Network connectivity requirements
- Container-to-container communication setup
- Troubleshooting steps for connection issues
- Testing procedures

### View Service Logs
```bash
# All services
docker compose -f docker-compose.ci.yml logs

# Specific service
docker compose -f docker-compose.ci.yml logs api
docker compose -f docker-compose.ci.yml logs qdrant
docker compose -f docker-compose.ci.yml logs milvus
docker compose -f docker-compose.ci.yml logs qa
```

---

## CI/CD Pipeline Issues

### Issue: "ERROR: API service failed to become healthy"

**Symptoms:**
```
Waiting for API service to be healthy...
ERROR: API service failed to become healthy
```

**Diagnosis Steps:**
1. Check API logs:
   ```bash
   docker compose -f docker-compose.ci.yml logs api
   ```

2. Verify port mapping:
   ```bash
   docker compose -f docker-compose.ci.yml ps api
   ```

3. Test healthcheck endpoint:
   ```bash
   docker compose -f docker-compose.ci.yml exec api curl -fsS http://localhost:8080/healthz
   ```

**Common Causes & Solutions:**

| Cause | Solution |
|-------|----------|
| Port 8080 already in use | Stop other services using port 8080 or change API port mapping |
| Missing environment variable | Check that required env vars are set (see ENVIRONMENT_VARIABLES.md) |
| Docker build failed | Rebuild with `docker compose build --no-cache api` |
| Insufficient memory | Increase Docker memory limit to at least 4GB |

### Issue: "timeout 120 bash -c 'until docker compose ps api | grep -q \"healthy\"'"

**Symptoms:**
The CI workflow times out while waiting for services to become healthy.

**Diagnosis:**
```bash
# Check if service is starting at all
docker compose -f docker-compose.ci.yml ps

# Check service status in detail
docker compose -f docker-compose.ci.yml ps --format json | jq
```

**Solutions:**
1. **Increase timeout**: For slow CI runners, increase timeout values in `.github/workflows/ci.yml`
   ```yaml
   timeout 240 bash -c '...'  # 4 minutes instead of 2
   ```

2. **Check healthcheck configuration**: Verify healthcheck settings in `docker-compose.ci.yml`
   ```yaml
   healthcheck:
     interval: 5s      # How often to check
     timeout: 3s       # How long to wait for response
     retries: 60       # Max retries before marking unhealthy
     start_period: 60s # Grace period on startup
   ```

3. **Review service startup logs**: Look for initialization errors
   ```bash
   docker compose -f docker-compose.ci.yml logs api | grep -i error
   ```

### Issue: "ERROR: Pre-flight validation failed"

**Symptoms:**
```
ERROR: Environment validation failed
  Variable: BENCH_POINTS
  Reason: must be >= 100, got 50
```

**Solution:**
Fix the environment variable as indicated in the error message. See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for valid ranges.

---

## Service Connectivity Issues

### Issue: "Connection refused" when accessing services

**Symptoms:**
```
curl: (7) Failed to connect to localhost port 8080: Connection refused
requests.exceptions.ConnectionError: HTTPConnectionPool
```

**Diagnosis:**
```bash
# Check if service is running
docker compose -f docker-compose.ci.yml ps

# Check if port is mapped
docker compose -f docker-compose.ci.yml ps --format json | jq '.[].Publishers'

# Check if service is listening on the port
docker compose -f docker-compose.ci.yml exec api netstat -tlnp | grep 8080
```

**Solutions:**

1. **Service not started:**
   ```bash
   docker compose -f docker-compose.ci.yml up -d api
   ```

2. **Port not exposed:**
   Add port mapping in `docker-compose.ci.yml`:
   ```yaml
   ports:
     - "8080:8080"
   ```

3. **Service binding to 127.0.0.1 only:**
   Set bind host to 0.0.0.0:
   ```yaml
   environment:
     - BIND_HOST=0.0.0.0
   ```

### Issue: Services healthy but endpoints not responding from host

**Symptoms:**
- Docker healthcheck passes (shows "healthy")
- `docker compose ps` shows healthy status
- `curl http://localhost:8080/healthz` fails from host

**Solution:**
This is a race condition where Docker's internal healthcheck passes before the port is fully bound on the host network. Add a small delay after healthcheck:

```bash
# Wait for healthy
timeout 120 bash -c 'until docker compose ps api | grep -q "healthy"; do sleep 2; done'

# Add 2-second delay for port binding
sleep 2

# Now test endpoint
curl -fsS http://localhost:8080/healthz
```

---

## Benchmark Failures

### Issue: "ERROR: pymilvus package not installed properly"

**Symptoms:**
```
ERROR: pymilvus package not installed properly
```

**Solution:**
```bash
pip install --upgrade pymilvus==2.5.0
python -c "import pymilvus; print(pymilvus.__version__)"
```

If issue persists:
```bash
pip uninstall pymilvus -y
pip install --no-cache-dir pymilvus==2.5.0
```

### Issue: "BenchmarkTimeout: Benchmark timeout during ingest"

**Symptoms:**
```
BenchmarkTimeout: Benchmark timeout during ingest
```

**Diagnosis:**
Check if the timeout is appropriate for your data size:
```python
# For 100k points with batch 2000:
# Expected time ≈ (100000 / 2000) * 5 seconds = 250 seconds
# Set timeout to at least 2x expected: 500 seconds
```

**Solutions:**

1. **Increase timeout:**
   ```bash
   export BENCH_TIMEOUT_SECONDS=1800  # 30 minutes
   ```

2. **Increase batch size** (if memory allows):
   ```bash
   export UPSERT_BATCH=5000
   ```

3. **Reduce data size** for testing:
   ```bash
   export BENCH_POINTS=10000
   export BENCH_Q=100
   ```

### Issue: "ERROR: bench_report.json status is not 'ok'"

**Symptoms:**
```
ERROR: bench_report.json status is not 'ok'
Status: error
```

**Diagnosis:**
```bash
cat MEF-Core_v1.0/assets/bench/bench_report.json | jq '.error'
cat MEF-Core_v1.0/assets/bench/bench_report.json | jq '.traceback'
```

**Common Causes:**

| Status | Cause | Solution |
|--------|-------|----------|
| `error` | Service connection failed | Verify service URLs and health |
| `timeout` | Operation exceeded timeout | Increase BENCH_TIMEOUT_SECONDS |
| `invalid_config` | Environment variable issue | Run preflight_check.py |

### Issue: "ERROR: compare.json has fewer than 2 successful targets"

**Symptoms:**
```
ERROR: compare.json has fewer than 2 successful targets
```

**Diagnosis:**
```bash
cat MEF-Core_v1.0/assets/bench/compare.json | jq '.targets[] | {name: .name, status: .status, error: .error}'
```

**Solutions:**

1. **Check which targets failed and why:**
   ```bash
   jq '.targets[] | select(.status != "ok")' assets/bench/compare.json
   ```

2. **Adjust REQUIRED_TARGETS** to match available services:
   ```bash
   export REQUIRED_TARGETS=mef,faiss  # Remove unavailable targets
   ```

3. **Debug specific target connection:**
   ```bash
   # For Qdrant
   curl http://localhost:6333/readyz
   
   # For Milvus
   python -c "from pymilvus import connections; connections.connect(host='localhost', port='19530')"
   ```

---

## Docker Issues

### Issue: "Cannot connect to the Docker daemon"

**Symptoms:**
```
Cannot connect to the Docker daemon at unix:///var/run/docker.sock
```

**Solutions:**
```bash
# Start Docker service
sudo systemctl start docker

# Check Docker is running
docker ps

# Add user to docker group (requires logout/login)
sudo usermod -aG docker $USER
```

### Issue: "docker compose command not found"

**Solutions:**
```bash
# Try with hyphen (older versions)
docker-compose --version

# Or install docker compose plugin
sudo apt-get update
sudo apt-get install docker-compose-plugin
```

### Issue: Out of disk space

**Symptoms:**
```
no space left on device
Error response from daemon: error creating overlay mount
```

**Solutions:**
```bash
# Clean up unused images and containers
docker system prune -a --volumes

# Check disk usage
docker system df

# Remove specific images
docker images | grep milvus | awk '{print $3}' | xargs docker rmi
```

### Issue: Services not cleaning up properly

**Symptoms:**
Old containers or volumes interfering with new runs.

**Solution:**
```bash
# Full cleanup
docker compose -f docker-compose.ci.yml down -v --remove-orphans

# Remove all stopped containers
docker container prune -f

# Remove all unused volumes
docker volume prune -f
```

---

## Performance Issues

### Issue: Benchmark runs very slowly

**Diagnosis:**
```bash
# Check system resources
docker stats

# Check if services are CPU/memory constrained
docker compose -f docker-compose.ci.yml top
```

**Solutions:**

1. **Increase Docker resources:**
   - Docker Desktop → Settings → Resources
   - Increase CPU limit to at least 4 cores
   - Increase memory limit to at least 8GB

2. **Reduce benchmark size:**
   ```bash
   export BENCH_POINTS=50000
   export BENCH_Q=100
   export COMPARE_LIMIT=500
   ```

3. **Optimize batch size:**
   ```bash
   # Test different batch sizes
   export UPSERT_BATCH=5000  # Larger batches = faster ingestion
   ```

4. **Use faster storage:**
   - Move Docker data directory to SSD
   - Ensure volumes are not on network mounts

### Issue: High memory usage / OOM kills

**Symptoms:**
```
Killed
Error: 137 (OOM)
docker: Error response from daemon: OOM command not allowed when used memory > 'docker run' memory
```

**Solutions:**

1. **Increase Docker memory limit:**
   ```bash
   # Docker Desktop: Settings → Resources → Memory → 8GB+
   ```

2. **Reduce concurrent operations:**
   ```bash
   export UPSERT_BATCH=1000  # Smaller batches
   export BENCH_POINTS=50000 # Fewer points
   ```

3. **Add memory limits to services:**
   ```yaml
   services:
     milvus:
       deploy:
         resources:
           limits:
             memory: 4G
   ```

---

## Data Issues

### Issue: "ERROR: Required file assets/bench/compare.json is missing"

**Symptoms:**
CI validation step fails because output files were not generated.

**Diagnosis:**
```bash
# Check if QA container ran successfully
docker compose -f docker-compose.ci.yml logs qa

# Check exit code
docker compose -f docker-compose.ci.yml ps qa
```

**Solutions:**

1. **QA container failed to run:** Check logs for errors
2. **Script failed early:** Look for Python exceptions in logs
3. **Permission issue:** Verify write permissions to assets/ directory

### Issue: Corrupted or invalid benchmark data

**Symptoms:**
```
ERROR: bench_report.json has invalid JSON
ValueError: could not convert string to float
```

**Solutions:**

1. **Delete corrupted files and retry:**
   ```bash
   rm -rf MEF-Core_v1.0/assets/bench/*.json
   rm -rf MEF-Core_v1.0/assets/bench/checkpoint.json
   ```

2. **Validate JSON files:**
   ```bash
   for f in assets/bench/*.json; do
     echo "Checking $f..."
     jq empty "$f" || echo "INVALID: $f"
   done
   ```

3. **Check for disk full issues:**
   ```bash
   df -h
   ```

---

## Getting Help

If you've tried the troubleshooting steps above and still have issues:

1. **Collect diagnostic information:**
   ```bash
   # Save all relevant logs
   docker compose -f docker-compose.ci.yml logs > docker-logs.txt
   docker compose -f docker-compose.ci.yml ps > docker-ps.txt
   env | grep -E 'BENCH_|QUALITY_|MILVUS_|QDRANT_' > env-vars.txt
   
   # Run preflight check and save output
   python tests/bench/preflight_check.py > preflight-output.txt 2>&1
   ```

2. **Check existing issues:**
   - Review [CI_IMPROVEMENTS_SUMMARY.md](../CI_IMPROVEMENTS_SUMMARY.md)
   - Review [CI_PIPELINE_FIX_SUMMARY.md](../CI_PIPELINE_FIX_SUMMARY.md)

3. **Include in your report:**
   - Environment details (OS, Docker version, Python version)
   - Exact error message and full stack trace
   - Steps to reproduce
   - Relevant log excerpts
   - Output from preflight check

---

## Appendix: Useful Commands

### Check All Service Health
```bash
#!/bin/bash
services=("api:8080/healthz" "qdrant:6333/readyz" "milvus:9091/healthz")
for service in "${services[@]}"; do
  url="http://${service}"
  if curl -fsS "$url" > /dev/null 2>&1; then
    echo "✓ $service is healthy"
  else
    echo "✗ $service is not responding"
  fi
done
```

### Reset Everything
```bash
#!/bin/bash
# Complete reset of benchmark environment
docker compose -f docker-compose.ci.yml down -v --remove-orphans
docker system prune -f
rm -rf MEF-Core_v1.0/assets/bench/*.json
rm -rf MEF-Core_v1.0/assets/golden/*.json
rm -rf MEF-Core_v1.0/.pytest_cache
rm -rf MEF-Core_v1.0/__pycache__
```

### Watch Service Logs in Real-Time
```bash
# All services
docker compose -f docker-compose.ci.yml logs -f

# Specific service with timestamps
docker compose -f docker-compose.ci.yml logs -f --timestamps api
```

### Debug Network Connectivity
```bash
# From host to service
curl -v http://localhost:8080/healthz

# From within container
docker compose -f docker-compose.ci.yml exec api curl -v http://localhost:8080/healthz

# Between containers
docker compose -f docker-compose.ci.yml exec qa curl -v http://api:8080/healthz
```
