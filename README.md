# Infinity Ledger - Enterprise-Ready Infrastructure

[![CI/CD](https://github.com/LashSesh/infinity-ledger/workflows/CI/badge.svg)](https://github.com/LashSesh/infinity-ledger/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Enterprise-grade infrastructure and CI/CD pipeline for Infinity Ledger, featuring MEF-Core (Mandorla Eigenstate Fractals) with robust deployment, monitoring, and security capabilities.

## 🚀 Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/LashSesh/infinity-ledger.git
cd infinity-ledger

# Set up environment
cp .env.development .env

# Start services
docker compose -f docker-compose.ci.yml --profile compare up -d

# Run tests
docker compose -f docker-compose.ci.yml --profile compare up qa
```

### Production Deployment

```bash
# Configure environment
cp .env.production .env
# Edit .env with your credentials

# Set up secrets
echo "your-api-token" | docker secret create mef_api_token -
echo "your-quality-token" | docker secret create quality_token -

# Deploy with monitoring
docker compose -f docker-compose.production.yml \
  --profile production \
  --profile monitoring \
  up -d

# Verify deployment
docker compose -f docker-compose.production.yml ps
curl http://localhost:8080/healthz
```

## 📋 Features

### Enterprise Infrastructure

✅ **Network Segmentation**
- Isolated networks for test, database, and monitoring
- Enhanced security through network-level isolation
- Custom subnet configuration for each network

✅ **Resource Management**
- CPU and memory limits for all services
- Resource reservations for guaranteed baseline performance
- Configurable via environment variables for different environments

✅ **High Availability**
- Comprehensive health checks for all services
- Automatic restart policies (on-failure with retry limits)
- Service dependency management with health-based startup

✅ **Centralized Logging**
- JSON-structured logs for all containers
- Automatic log rotation and retention policies
- Labeled logs for easy filtering and analysis

✅ **Monitoring & Observability**
- Prometheus metrics collection
- Grafana dashboards for visualization
- Service health and performance monitoring
- Resource utilization tracking

✅ **Security & Secrets Management**
- Support for Docker Secrets
- HashiCorp Vault integration
- AWS Secrets Manager compatibility
- Environment-specific authentication

✅ **CI/CD Pipeline**
- Retry logic with exponential backoff
- Comprehensive error handling and diagnostics
- Artifact collection and validation
- Multi-environment support (dev, staging, production)

## 📚 Documentation

- **[INFRASTRUCTURE.md](INFRASTRUCTURE.md)**: Complete infrastructure documentation
  - Architecture overview
  - Network segmentation
  - Service configuration
  - Resource management
  - Monitoring setup
  - Deployment procedures
  - Troubleshooting guide

- **[SECRETS_MANAGEMENT.md](SECRETS_MANAGEMENT.md)**: Secrets and credentials management
  - Development environment setup
  - CI/CD secrets (GitHub Actions)
  - Staging deployment (Docker Secrets)
  - Production deployment (Vault, AWS Secrets Manager)
  - Secret rotation procedures
  - Auditing and compliance

- **[MEF-Core_v1.0/README.md](MEF-Core_v1.0/README.md)**: MEF-Core system documentation
  - System overview and architecture
  - Installation and quick start
  - API documentation
  - Development guide

- **[MEF-Core_v1.0/README_bench.md](MEF-Core_v1.0/README_bench.md)**: Benchmark documentation
  - Benchmark suite overview
  - Cross-database comparisons
  - Configuration options
  - CI/CD integration

## 🏗️ Architecture

### Service Components

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
│  ┌──────────┐      ┌─────▼─────┐      ┌──────────────┐        │
│  │  Qdrant  │◀─────│    API    │─────▶│   Milvus     │        │
│  │  Vector  │      │  Service  │      │   Vector     │        │
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

### Service Descriptions

| Service | Purpose | Networks | Ports |
|---------|---------|----------|-------|
| **API** | MEF-Core API server | test, db, monitoring | 8080 |
| **Qdrant** | Vector similarity search | db | 6333 |
| **Milvus** | Vector database | db | 19530, 9091 |
| **FAISS-API** | FAISS HTTP wrapper | test | 8090 |
| **QA** | Test and benchmark execution | test, db | - |
| **Prometheus** | Metrics collection | monitoring, test | 9090 |
| **Grafana** | Metrics visualization | monitoring | 3000 |

## 🔧 Configuration

### Environment Files

Four environment templates are provided for different deployment scenarios:

1. **`.env.example`**: Complete template with all configuration options
2. **`.env.development`**: Lightweight configuration for local development
3. **`.env.staging`**: Production-like configuration for staging
4. **`.env.production`**: Full production configuration with all features

### Key Configuration Variables

```bash
# Environment
ENVIRONMENT=production              # development, staging, production

# Authentication
AUTH_TOKEN_REQUIRED=true           # Enable/disable authentication
MEF_API_TOKEN=<your-token>         # API authentication token

# Service Endpoints
QUALITY_BASE_URL=http://api:8080   # API endpoint
QDRANT_URL=http://qdrant:6333      # Qdrant connection
MILVUS_HOST=milvus                 # Milvus host
MILVUS_PORT=19530                  # Milvus port

# Benchmarks
BENCH_COMPARE=1                     # Enable cross-DB comparison
BENCH_TARGETS=mef,faiss,qdrant,milvus  # Comparison targets
COMPARE_LIMIT=500                   # Dataset size limit

# Resources
API_CPU_LIMIT=4.0                   # API CPU limit (cores)
API_MEMORY_LIMIT=4G                 # API memory limit
MILVUS_CPU_LIMIT=8.0               # Milvus CPU limit (cores)
MILVUS_MEMORY_LIMIT=8G             # Milvus memory limit

# Monitoring
LOG_LEVEL=info                      # Logging level
ENABLE_METRICS=true                 # Enable Prometheus metrics
```

See `.env.example` for complete configuration options.

## 🐳 Docker Compose Files

### docker-compose.ci.yml

CI/CD and testing configuration with:
- All core services (API, Qdrant, Milvus, QA)
- Network segmentation (test, db)
- Resource limits
- Health checks
- Centralized logging
- Restart policies

**Usage**:
```bash
# Start with compare profile
docker compose -f docker-compose.ci.yml --profile compare up -d

# Run tests
docker compose -f docker-compose.ci.yml --profile compare up qa
```

### docker-compose.production.yml

Production deployment with:
- All CI features plus:
- Monitoring stack (Prometheus, Grafana)
- Docker Secrets support
- Data persistence volumes
- Production resource limits
- Monitoring network

**Usage**:
```bash
# Deploy with monitoring
docker compose -f docker-compose.production.yml \
  --profile production \
  --profile monitoring \
  up -d
```

## 🧪 Testing

### Run All Tests

```bash
cd MEF-Core_v1.0
pip install -r requirements.txt
pytest tests/bench/ -v
```

### Enterprise Infrastructure Tests

```bash
# Test infrastructure configuration
pytest tests/bench/test_enterprise_infrastructure.py -v

# Test service health checks
pytest tests/bench/test_ci_service_health.py -v

# Test cross-DB integration
pytest tests/bench/test_cross_db_integration.py -v
```

### Integration Tests

```bash
# Start services
docker compose -f docker-compose.ci.yml --profile compare up -d

# Run integration tests
docker compose -f docker-compose.ci.yml --profile compare up qa

# Check results
ls -la MEF-Core_v1.0/assets/bench/
```

## 🔒 Security

### Best Practices

1. **Never commit secrets** to version control
2. **Use Docker Secrets or Vault** in production
3. **Enable authentication** (AUTH_TOKEN_REQUIRED=true)
4. **Rotate secrets regularly** (every 30-90 days)
5. **Use network segmentation** to isolate services
6. **Enable audit logging** for compliance
7. **Keep images updated** with security patches

### Secrets Management

See [SECRETS_MANAGEMENT.md](SECRETS_MANAGEMENT.md) for comprehensive guide on:
- Development environment setup
- CI/CD secrets (GitHub Actions)
- Staging deployment (Docker Secrets)
- Production deployment (Vault, AWS Secrets Manager)
- Secret rotation procedures

## 📊 Monitoring

### Prometheus

Access Prometheus at `http://localhost:9090`

**Key Metrics**:
- Service health status
- Request rate and latency
- Resource utilization (CPU, memory)
- Error rates

### Grafana

Access Grafana at `http://localhost:3000` (default: admin/admin)

**Dashboards**:
- Service Health Overview
- Request Latency and Throughput
- Resource Utilization
- Database Performance

### Logs

View centralized logs:
```bash
# All services
docker compose -f docker-compose.ci.yml logs -f

# Specific service
docker compose -f docker-compose.ci.yml logs -f api

# Last 100 lines
docker compose -f docker-compose.ci.yml logs --tail=100 api
```

## 🚢 CI/CD Pipeline

### GitHub Actions

The CI pipeline (`.github/workflows/ci.yml`) includes:

1. **Pre-flight Validation**: Environment and dependency checks
2. **Service Startup**: Health-checked service initialization with retry logic
3. **Benchmark Execution**: Comprehensive benchmark suite
4. **Output Validation**: Verify all artifacts are generated correctly
5. **Artifact Upload**: Store results for analysis

### Key Features

- **Retry Logic**: Automatic retries with exponential backoff
- **Error Handling**: Comprehensive logging and diagnostics
- **Health Verification**: All services must be healthy before tests
- **Resource Limits**: Prevent resource exhaustion
- **Timeout Management**: Explicit timeouts for all steps

### Artifacts

The pipeline generates and uploads:
- `bench_report.json`: Benchmark results
- `recall_report.json`: Recall evaluation
- `compare.json` / `compare.md`: Cross-DB comparison
- `server.log` / `bench.log`: Service logs
- Golden test results

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `pytest tests/bench/ -v`
5. Validate configuration: `docker compose -f docker-compose.ci.yml --profile compare config`
6. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/LashSesh/infinity-ledger/issues)
- **Documentation**: See docs/ directory
- **CI/CD Logs**: Check GitHub Actions tab

## 🔗 Related Projects

- **MEF-Core**: Mandorla Eigenstate Fractals core system
- **Qdrant**: Vector similarity search engine
- **Milvus**: Open-source vector database
- **FAISS**: Facebook AI Similarity Search

---

**Last Updated**: 2025-10-13  
**Version**: 1.0.0 (Enterprise-Ready Infrastructure)
