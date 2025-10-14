# Infrastructure Documentation - Infinity Ledger

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Network Segmentation](#network-segmentation)
4. [Service Configuration](#service-configuration)
5. [Resource Management](#resource-management)
6. [Monitoring & Observability](#monitoring--observability)
7. [Security & Secrets Management](#security--secrets-management)
8. [Environment Configuration](#environment-configuration)
9. [Deployment Procedures](#deployment-procedures)
10. [Troubleshooting](#troubleshooting)
11. [CI/CD Pipeline](#cicd-pipeline)

---

## Overview

The Infinity Ledger infrastructure is designed for enterprise-grade reliability, security, and observability. The system consists of:

- **MEF Core API**: Main application server
- **Vector Databases**: Qdrant, Milvus, FAISS
- **Testing Infrastructure**: QA container for benchmarks
- **Monitoring Stack**: Prometheus, Grafana (optional)

### Design Principles

1. **Reliability**: All services have health checks, restart policies, and resource limits
2. **Security**: Network segmentation, secrets management, authentication
3. **Observability**: Centralized logging, metrics collection, monitoring dashboards
4. **Scalability**: Resource limits, horizontal scaling support
5. **Maintainability**: Comprehensive documentation, environment-based configuration

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Test Network                            │
│  ┌──────────┐      ┌──────────┐      ┌──────────────┐         │
│  │    QA    │─────▶│   API    │─────▶│  FAISS-API   │         │
│  │Container │      │ Service  │      │   Service    │         │
│  └──────────┘      └────┬─────┘      └──────────────┘         │
└──────────────────────────┼──────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                    DB Network                                   │
│                           │                                      │
│  ┌──────────┐      ┌─────▼─────┐      ┌──────────────┐        │
│  │  Qdrant  │◀─────│    API    │      │   Milvus     │        │
│  │  Vector  │      │  Service  │─────▶│   Vector     │        │
│  │    DB    │      └───────────┘      │     DB       │        │
│  └──────────┘                         └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────┐
│                  Monitoring Network                             │
│  ┌──────────┐      ┌─────▼─────┐      ┌──────────────┐        │
│  │Prometheus│◀─────│    API    │      │   Grafana    │        │
│  │ Metrics  │      │  Service  │─────▶│  Dashboards  │        │
│  └──────────┘      └───────────┘      └──────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Network Segmentation

The infrastructure uses three isolated networks for security and performance:

### 1. Test Network (172.20.0.0/16)
- **Purpose**: Communication between QA container and application services
- **Services**: QA, API, FAISS-API
- **Security**: Isolated from production databases

### 2. DB Network (172.21.0.0/16)
- **Purpose**: Database communication and API-to-DB connections
- **Services**: API, Qdrant, Milvus
- **Security**: No direct external access, only through API

### 3. Monitoring Network (172.22.0.0/16)
- **Purpose**: Metrics collection and monitoring
- **Services**: Prometheus, Grafana, all monitored services
- **Security**: Read-only metrics access

### Network Configuration

```yaml
networks:
  test-network:
    driver: bridge
    name: infinity-ledger-test
    ipam:
      config:
        - subnet: 172.20.0.0/16

  db-network:
    driver: bridge
    name: infinity-ledger-db
    ipam:
      config:
        - subnet: 172.21.0.0/16

  monitoring-network:
    driver: bridge
    name: infinity-ledger-monitoring
    ipam:
      config:
        - subnet: 172.22.0.0/16
```

---

## Service Configuration

### API Service

**Purpose**: Main MEF Core API server

**Configuration**:
- **Image**: Custom build from `./MEF-Core_v1.0`
- **Ports**: 8080 (HTTP)
- **Networks**: test-network, db-network, monitoring-network
- **Health Check**: `curl -fsS http://localhost:8080/healthz` every 5s
- **Restart Policy**: `on-failure:3` (retry 3 times)

**Resource Limits** (Configurable):
- CPU: 2.0 cores (default), up to 4.0 in production
- Memory: 2GB (default), up to 4GB in production
- Reservation: 512MB minimum

**Environment Variables**:
- `BIND_HOST`: 0.0.0.0
- `PORT`: 8080
- `AUTH_TOKEN_REQUIRED`: false (CI), true (production)
- `LOG_LEVEL`: info/debug
- `ENABLE_METRICS`: true (production)

### Qdrant Service

**Purpose**: Vector similarity search database

**Configuration**:
- **Image**: `qdrant/qdrant:v1.8.3`
- **Ports**: 6333 (HTTP API)
- **Networks**: db-network
- **Health Check**: TCP connection test every 2s
- **Restart Policy**: `on-failure:5`

**Resource Limits**:
- CPU: 2.0 cores (default), up to 4.0 in production
- Memory: 2GB (default), up to 4GB in production
- Reservation: 512MB minimum

**Persistence** (Optional):
```yaml
volumes:
  - qdrant-data:/qdrant/storage
```

### Milvus Service

**Purpose**: Open-source vector database

**Configuration**:
- **Image**: `milvusdb/milvus:v2.3.3`
- **Ports**: 19530 (gRPC), 9091 (HTTP/Metrics)
- **Networks**: db-network
- **Health Check**: `curl http://localhost:9091/healthz` every 5s
- **Restart Policy**: `on-failure:5`

**Resource Limits** (Higher requirements):
- CPU: 4.0 cores (default), up to 8.0 in production
- Memory: 4GB (default), up to 8GB in production
- Reservation: 1GB minimum

**Persistence** (Optional):
```yaml
volumes:
  - milvus-data:/var/lib/milvus
```

### QA Container

**Purpose**: Benchmark and test execution

**Configuration**:
- **Image**: `python:3.11-slim`
- **Networks**: test-network, db-network
- **Restart Policy**: `no` (one-shot execution)
- **Dependencies**: Waits for api, qdrant, milvus to be healthy

**Resource Limits**:
- CPU: 2.0 cores (default)
- Memory: 4GB (default)
- Reservation: 1GB minimum

---

## Resource Management

### Default Resource Allocations

| Service    | CPU Limit | Memory Limit | CPU Reserved | Memory Reserved |
|------------|-----------|--------------|--------------|-----------------|
| API        | 2.0       | 2GB          | 0.5          | 512MB           |
| Qdrant     | 2.0       | 2GB          | 0.5          | 512MB           |
| Milvus     | 4.0       | 4GB          | 1.0          | 1GB             |
| QA         | 2.0       | 4GB          | 1.0          | 1GB             |
| FAISS-API  | 2.0       | 2GB          | 0.5          | 512MB           |
| Prometheus | 1.0       | 1GB          | 0.25         | 256MB           |
| Grafana    | 1.0       | 512MB        | 0.25         | 128MB           |

### Production Resource Allocations

For production deployments, increase limits via environment variables:

```bash
# API Service
API_CPU_LIMIT=4.0
API_MEMORY_LIMIT=4G
API_MEMORY_RESERVATION=1G

# Qdrant
QDRANT_CPU_LIMIT=4.0
QDRANT_MEMORY_LIMIT=4G

# Milvus
MILVUS_CPU_LIMIT=8.0
MILVUS_MEMORY_LIMIT=8G
MILVUS_MEMORY_RESERVATION=2G
```

### Monitoring Resource Usage

Use `docker stats` to monitor real-time resource usage:

```bash
docker stats $(docker ps --format '{{.Names}}' | grep infinity-ledger)
```

---

## Monitoring & Observability

### Centralized Logging

All services use JSON-structured logging with the following configuration:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"        # Max log file size
    max-file: "3"          # Number of log files to retain
    labels: "service=api,environment=production"
```

### Viewing Logs

```bash
# View logs for a specific service
docker compose -f docker-compose.ci.yml logs -f api

# View logs for all services
docker compose -f docker-compose.ci.yml logs -f

# View logs with timestamps
docker compose -f docker-compose.ci.yml logs -t api

# View last 100 lines
docker compose -f docker-compose.ci.yml logs --tail=100 api
```

### Prometheus Metrics

**Enabled by default in production**, Prometheus collects metrics from:
- MEF API Service (port 9090)
- Qdrant (port 6333)
- Milvus (port 9091)
- FAISS-API (port 8090)

**Configuration**: `monitoring/prometheus.yml`

**Key Metrics**:
- Request rate and latency
- Resource utilization (CPU, memory)
- Error rates
- Health check status

### Grafana Dashboards

Grafana provides visualization of Prometheus metrics:

**Access**: http://localhost:3000 (default credentials: admin/admin)

**Dashboards**:
- Service Health Overview
- Request Latency and Throughput
- Resource Utilization
- Database Performance

**Configuration**:
- Datasources: `monitoring/grafana/datasources/prometheus.yml`
- Dashboards: `monitoring/grafana/dashboards/`

### Starting Monitoring Stack

```bash
# Start with monitoring profile
docker compose -f docker-compose.production.yml --profile monitoring up -d

# Verify monitoring services
docker compose -f docker-compose.production.yml ps prometheus grafana
```

---

## Security & Secrets Management

### Authentication

**CI/Development**: Authentication disabled for testing
```yaml
AUTH_TOKEN_REQUIRED=false
```

**Production**: Authentication required
```yaml
AUTH_TOKEN_REQUIRED=true
```

### Secrets Management

#### Option 1: Docker Secrets (Recommended for Production)

```bash
# Create secrets
echo "your-api-token" | docker secret create mef_api_token -
echo "your-quality-token" | docker secret create quality_token -

# Start services with secrets
docker compose -f docker-compose.production.yml --profile production up -d
```

#### Option 2: Environment Variables (Development/Staging)

```bash
# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Start services
docker compose -f docker-compose.ci.yml --profile compare up -d
```

#### Option 3: External Secret Management (Enterprise)

Integrate with:
- **HashiCorp Vault**: Use vault agent for secret injection
- **AWS Secrets Manager**: Use ECS task definitions with secrets
- **Azure Key Vault**: Use managed identities
- **Google Secret Manager**: Use service account credentials

**Example Vault Integration**:
```bash
# Install vault agent
vault agent -config=vault-agent.hcl

# Configure docker-compose to read from vault-rendered files
environment:
  - MEF_API_TOKEN_FILE=/run/secrets/mef_api_token
```

### Network Security

1. **Network Isolation**: Services isolated by network (test, db, monitoring)
2. **No External DB Access**: Databases only accessible through API
3. **Firewall Rules**: Configure host firewall to restrict external access
4. **TLS/SSL**: Enable HTTPS in production (use reverse proxy like Nginx)

### Best Practices

1. **Never commit secrets** to version control
2. **Rotate secrets regularly** (every 90 days)
3. **Use principle of least privilege** for service accounts
4. **Enable audit logging** for secret access
5. **Monitor for security events** in logs

---

## Environment Configuration

### Environment Files

The repository includes environment templates for different deployments:

1. **`.env.example`**: Template with all configuration options
2. **`.env.development`**: Development settings (lightweight)
3. **`.env.staging`**: Staging settings (production-like)
4. **`.env.production`**: Production settings (full resources)

### Using Environment Files

```bash
# Development
docker compose --env-file .env.development up

# Staging
docker compose --env-file .env.staging up

# Production
docker compose -f docker-compose.production.yml --env-file .env.production up
```

### Key Configuration Variables

#### Service Endpoints
```bash
QUALITY_BASE_URL=http://api:8080
QDRANT_URL=http://qdrant:6333
MILVUS_HOST=milvus
MILVUS_PORT=19530
```

#### Benchmark Configuration
```bash
BENCH_POINTS=100000      # Dataset size
BENCH_Q=200              # Number of queries
BENCH_K=10               # Top-k results
COMPARE_LIMIT=500        # Cross-DB comparison limit
```

#### Resource Limits
```bash
API_CPU_LIMIT=2.0
API_MEMORY_LIMIT=2G
QDRANT_CPU_LIMIT=2.0
MILVUS_CPU_LIMIT=4.0
```

#### Logging & Monitoring
```bash
LOG_LEVEL=info           # debug, info, warning, error
LOG_FORMAT=json          # json, text
ENABLE_METRICS=true      # Enable Prometheus metrics
```

---

## Deployment Procedures

### Local Development

```bash
# 1. Copy environment template
cp .env.development .env

# 2. Start services
docker compose -f docker-compose.ci.yml --profile compare up -d

# 3. Verify services are healthy
docker compose -f docker-compose.ci.yml ps

# 4. Run tests
docker compose -f docker-compose.ci.yml --profile compare up qa

# 5. Stop services
docker compose -f docker-compose.ci.yml down
```

### Staging Deployment

```bash
# 1. Set environment
export ENVIRONMENT=staging

# 2. Load staging config
cp .env.staging .env

# 3. Start services with monitoring
docker compose -f docker-compose.production.yml \
  --profile staging \
  --profile monitoring \
  up -d

# 4. Verify health
docker compose -f docker-compose.production.yml ps

# 5. Check logs
docker compose -f docker-compose.production.yml logs -f
```

### Production Deployment

```bash
# 1. Set up secrets (using Docker Swarm or external secret manager)
echo "production-api-token" | docker secret create mef_api_token -
echo "production-quality-token" | docker secret create quality_token -

# 2. Load production config
cp .env.production .env

# 3. Start services
docker compose -f docker-compose.production.yml \
  --profile production \
  --profile monitoring \
  up -d

# 4. Verify all services are healthy
docker compose -f docker-compose.production.yml ps

# 5. Test API endpoint
curl -fsS http://localhost:8080/healthz

# 6. Check monitoring dashboards
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000
```

### Rolling Updates

```bash
# 1. Pull latest images
docker compose -f docker-compose.production.yml pull

# 2. Restart services one by one (zero-downtime with multiple replicas)
docker compose -f docker-compose.production.yml up -d --no-deps --scale api=2 api

# 3. Verify health before proceeding
docker compose -f docker-compose.production.yml ps api

# 4. Update other services
docker compose -f docker-compose.production.yml up -d --no-deps qdrant
docker compose -f docker-compose.production.yml up -d --no-deps milvus
```

### Backup Procedures

```bash
# 1. Backup Qdrant data
docker run --rm -v infinity-ledger-qdrant-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/qdrant-backup-$(date +%Y%m%d).tar.gz /data

# 2. Backup Milvus data
docker run --rm -v infinity-ledger-milvus-data:/data -v $(pwd):/backup \
  ubuntu tar czf /backup/milvus-backup-$(date +%Y%m%d).tar.gz /data

# 3. Backup configuration
tar czf config-backup-$(date +%Y%m%d).tar.gz .env* docker-compose*.yml monitoring/
```

### Restore Procedures

```bash
# 1. Stop services
docker compose -f docker-compose.production.yml down

# 2. Restore Qdrant data
docker run --rm -v infinity-ledger-qdrant-data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/qdrant-backup-YYYYMMDD.tar.gz -C /

# 3. Restore Milvus data
docker run --rm -v infinity-ledger-milvus-data:/data -v $(pwd):/backup \
  ubuntu tar xzf /backup/milvus-backup-YYYYMMDD.tar.gz -C /

# 4. Restart services
docker compose -f docker-compose.production.yml up -d
```

---

## Troubleshooting

### Common Issues

#### 1. Services Not Becoming Healthy

**Symptoms**: Services stuck in "starting" state

**Diagnosis**:
```bash
# Check service logs
docker compose -f docker-compose.ci.yml logs api

# Check container status
docker compose -f docker-compose.ci.yml ps

# Inspect health check
docker inspect $(docker compose -f docker-compose.ci.yml ps -q api) | jq '.[0].State.Health'
```

**Solutions**:
- Increase health check start period
- Check resource availability (CPU, memory)
- Verify network connectivity

#### 2. Network Connectivity Issues

**Symptoms**: Services can't communicate with each other

**Diagnosis**:
```bash
# Check network configuration
docker network inspect infinity-ledger-test

# Test connectivity from QA container
docker compose -f docker-compose.ci.yml run --rm qa \
  curl -fsS http://api:8080/healthz
```

**Solutions**:
- Verify all services on correct networks
- Check firewall rules
- Restart Docker daemon

#### 3. Resource Exhaustion

**Symptoms**: Services crashing or performing poorly

**Diagnosis**:
```bash
# Check resource usage
docker stats

# Check system resources
free -h
df -h
```

**Solutions**:
- Increase resource limits
- Scale down number of services
- Add more system resources

#### 4. Data Persistence Issues

**Symptoms**: Data lost after container restart

**Diagnosis**:
```bash
# Check if volumes are configured
docker volume ls | grep infinity-ledger

# Inspect volume
docker volume inspect infinity-ledger-qdrant-data
```

**Solutions**:
- Uncomment volume mounts in docker-compose
- Verify volume driver
- Check disk space

### Debug Mode

Enable debug logging for troubleshooting:

```bash
# Set debug log level
export LOG_LEVEL=debug

# Restart services
docker compose -f docker-compose.ci.yml --profile compare up -d

# View debug logs
docker compose -f docker-compose.ci.yml logs -f
```

### Performance Tuning

#### API Service
```bash
# Increase workers
export UVICORN_WORKERS=4

# Increase memory
export API_MEMORY_LIMIT=4G
```

#### Database Services
```bash
# Increase Milvus resources
export MILVUS_CPU_LIMIT=8.0
export MILVUS_MEMORY_LIMIT=8G

# Increase Qdrant resources
export QDRANT_CPU_LIMIT=4.0
export QDRANT_MEMORY_LIMIT=4G
```

---

## CI/CD Pipeline

### Pipeline Overview

The GitHub Actions CI/CD pipeline consists of the following stages:

1. **Pre-flight Validation**: Environment checks, dependency verification
2. **Service Startup**: Start and verify health of all services
3. **Benchmark Execution**: Run comprehensive benchmark suite
4. **Validation**: Verify outputs and results
5. **Artifact Upload**: Store results and logs

### Pipeline Configuration

**File**: `.github/workflows/ci.yml`

**Key Features**:
- Retry logic for flaky tests
- Exponential backoff for service startup
- Comprehensive error reporting
- Artifact collection
- Output validation

### Retry Logic

The pipeline includes retry mechanisms at multiple levels:

1. **Service Startup**: 3 retries with exponential backoff
2. **Endpoint Verification**: 3 retries with exponential backoff
3. **QA Container Execution**: 2 attempts with 5s pause

### Error Handling

Each step includes detailed error handling:
- Capture and display service logs on failure
- Display container status information
- Clear error messages for debugging
- Non-zero exit codes for failures

### Environment Variables

All configuration is externalized via environment variables:
```yaml
env:
  AUTH_TOKEN_REQUIRED: "false"
  BENCH_COMPARE: "1"
  BENCH_TARGETS: "mef,faiss,qdrant,milvus"
  REQUIRED_TARGETS: "mef,faiss,qdrant"
  # ... (see ci.yml for complete list)
```

### Artifacts

The pipeline collects and uploads:
- Benchmark results (JSON, Markdown)
- Service logs
- Golden test results
- Debug information

**Retention**: 90 days

### Monitoring CI Performance

Key metrics to monitor:
- Pipeline duration
- Service startup time
- Test pass rate
- Artifact generation success rate

---

## Conclusion

This infrastructure provides a robust, secure, and observable foundation for running Infinity Ledger in production. Key highlights:

✅ **Reliability**: Health checks, restart policies, retry logic
✅ **Security**: Network segmentation, secrets management, authentication
✅ **Observability**: Centralized logging, Prometheus metrics, Grafana dashboards
✅ **Scalability**: Resource limits, horizontal scaling, environment-based config
✅ **Maintainability**: Comprehensive documentation, clear procedures

For additional help or questions, please refer to:
- **README.md**: Getting started guide
- **README_bench.md**: Benchmark documentation
- **ARCHITECTURE.md**: System architecture details

---

**Last Updated**: 2025-10-13
**Version**: 1.0.0
