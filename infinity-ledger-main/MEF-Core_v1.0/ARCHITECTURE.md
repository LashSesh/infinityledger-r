# MEF-Core Architecture Overview

This document provides a high-level overview of the MEF-Core benchmark and testing infrastructure architecture.

## Table of Contents

- [System Architecture](#system-architecture)
- [Components](#components)
- [Data Flow](#data-flow)
- [Service Dependencies](#service-dependencies)
- [Testing Strategy](#testing-strategy)
- [Monitoring and Observability](#monitoring-and-observability)

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CI/CD Pipeline                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Pre-Flight Validation                                        │
│     - Environment variables                                      │
│     - Python dependencies                                        │
│     - Directory structure                                        │
│                                                                  │
│  2. Service Orchestration                                        │
│     - Start all required services                                │
│     - Health check verification                                  │
│     - Endpoint validation                                        │
│                                                                  │
│  3. Benchmark Execution                                          │
│     - Benchmark runner                                           │
│     - Recall evaluation                                          │
│     - Golden tests                                               │
│     - Cross-DB comparison                                        │
│                                                                  │
│  4. Validation & Artifacts                                       │
│     - Output file validation                                     │
│     - Report generation                                          │
│     - Artifact upload                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Components

### Core Services

#### 1. MEF-Core API Service
- **Purpose**: Main vector database service with Proof-of-Resonance validation
- **Port**: 8080
- **Healthcheck**: `/healthz`, `/readyz`
- **Dependencies**: None (standalone)
- **Key Features**:
  - Vector storage and retrieval
  - Proof-of-Resonance validation
  - Quality scoring and indexing
  - RESTful API interface

#### 2. Qdrant Vector Database
- **Purpose**: External vector database for comparison benchmarks
- **Port**: 6333
- **Healthcheck**: `/readyz`
- **Image**: `qdrant/qdrant:v1.8.3`
- **Key Features**:
  - High-performance vector search
  - gRPC and HTTP APIs
  - Filtering and payload support

#### 3. Milvus Vector Database
- **Purpose**: External vector database for comparison benchmarks
- **Ports**: 19530 (gRPC), 9091 (health)
- **Healthcheck**: `/healthz` on port 9091
- **Image**: `milvusdb/milvus:v2.3.3`
- **Mode**: Standalone (includes QueryCoord, DataNode, RootCoord, Proxy)
- **Key Features**:
  - Distributed vector database
  - Multiple index types (HNSW, IVF, etc.)
  - Rich query language

#### 4. FAISS HTTP API
- **Purpose**: HTTP wrapper for FAISS library for comparison benchmarks
- **Port**: 8090
- **Healthcheck**: `POST /clear`
- **Key Features**:
  - Fast similarity search
  - Multiple index algorithms
  - In-memory operation

### Support Services

#### QA Container
- **Purpose**: Orchestrates benchmark execution and validation
- **Dependencies**: API, Qdrant, Milvus (all must be healthy)
- **Execution Phases**:
  1. Install Python dependencies
  2. Run pre-flight validation
  3. Execute benchmark suite
  4. Generate summary report

### Infrastructure Components

#### 1. Environment Validator (`env_validator.py`)
- **Purpose**: Type-safe validation of environment variables
- **Features**:
  - Integer validation with range checks
  - Float validation with range checks
  - URL validation with scheme checking
  - Boolean parsing (multiple formats)
  - Comma-separated list validation
- **Usage**: Used by preflight check and can be imported by any script

#### 2. Pre-Flight Check (`preflight_check.py`)
- **Purpose**: Comprehensive environment validation before execution
- **Validations**:
  - All environment variables (30+ variables)
  - Python package availability
  - Directory structure and permissions
- **Output**: Detailed validation report with clear error messages

#### 3. Structured Logger (`logger.py`)
- **Purpose**: Enhanced logging with context and timing
- **Features**:
  - JSON and human-readable output modes
  - Context management (component, operation, request_id)
  - Operation timing with context managers
  - Exception capture with tracebacks
  - File and stream output
- **Usage**: Available for all benchmark and test scripts

---

## Data Flow

### Benchmark Execution Flow

```
┌──────────────┐
│   Start CI   │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────┐
│  Pre-Flight Validation       │
│  - Validate env vars         │
│  - Check dependencies        │
│  - Verify directories        │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Start Services              │
│  - docker compose up -d      │
│  - Wait for health checks    │
│  - Verify endpoints          │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Benchmark Runner            │
│  1. Generate test corpus     │
│  2. Upsert vectors           │
│  3. Execute search queries   │
│  4. Measure latencies        │
│  5. Generate report          │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Recall Evaluation           │
│  1. Generate golden set      │
│  2. Search each DB           │
│  3. Compare results          │
│  4. Calculate recall@k       │
│  5. Generate report          │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Golden Tests                │
│  1. Generate samples         │
│  2. Execute operations       │
│  3. Validate proofs          │
│  4. Check consistency        │
│  5. Generate report          │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Cross-DB Compare            │
│  1. Connect to all targets   │
│  2. Run same workload        │
│  3. Measure metrics          │
│  4. Compare performance      │
│  5. Generate comparison      │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Validate Outputs            │
│  - Check all files exist     │
│  - Validate JSON structure   │
│  - Verify metrics            │
│  - Check completeness        │
└──────┬───────────────────────┘
       │
       ▼
┌──────────────────────────────┐
│  Upload Artifacts            │
│  - Benchmark reports         │
│  - Comparison results        │
│  - Service logs              │
│  - Golden test data          │
└──────────────────────────────┘
```

---

## Service Dependencies

### Dependency Graph

```
                    ┌─────────────┐
                    │   CI/CD     │
                    │  Workflow   │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
         ┌────────┐  ┌────────┐  ┌────────┐
         │  API   │  │ Qdrant │  │ Milvus │
         │ (MEF)  │  │        │  │        │
         └────┬───┘  └────┬───┘  └────┬───┘
              │           │           │
              └───────────┼───────────┘
                          │
                          ▼
                   ┌─────────────┐
                   │ QA Container│
                   │  (Benchmarks)│
                   └─────────────┘
```

### Health Check Dependencies

All services must report `healthy` status before QA container starts:

1. **API Service**: `service_healthy` condition
   - Checks: `curl http://localhost:8080/healthz`
   - Retry: 60 attempts, 5s interval
   - Timeout: 60s start period

2. **Qdrant Service**: `service_healthy` condition
   - Checks: `curl http://localhost:6333/readyz`
   - Retry: 90 attempts, 2s interval

3. **Milvus Service**: `service_healthy` condition
   - Checks: `curl http://localhost:9091/healthz`
   - Retry: 60 attempts, 5s interval
   - Timeout: 30s start period

### Network Architecture

```
┌─────────────────────────────────────────┐
│          Docker Network (default)       │
│                                         │
│  ┌─────────┐      ┌──────────┐         │
│  │   API   │◄────►│  Qdrant  │         │
│  │  :8080  │      │  :6333   │         │
│  └────▲────┘      └──────────┘         │
│       │                                 │
│       │           ┌──────────┐         │
│       └──────────►│  Milvus  │         │
│                   │ :19530   │         │
│                   │ :9091    │         │
│                   └────▲─────┘         │
│                        │               │
│                  ┌─────┴─────┐        │
│                  │    QA     │        │
│                  │ Container │        │
│                  └───────────┘        │
└─────────────────────────────────────────┘
           │                    │
           ▼                    ▼
    Host :8080            Host :6333
    (API access)         (Qdrant access)
```

---

## Testing Strategy

### Test Pyramid

```
                    ┌──────────────────┐
                    │   E2E/CI Tests   │
                    │  (8 test files)  │
                    └──────────────────┘
                           ▲
                           │
              ┌────────────┴────────────┐
              │  Integration Tests       │
              │  (Cross-DB compare,      │
              │   Service health)        │
              └────────────┬─────────────┘
                           │
         ┌─────────────────┴──────────────────┐
         │        Unit Tests                   │
         │  (env_validator: 45 tests           │
         │   logger: 25 tests                  │
         │   Benchmark components)             │
         └─────────────────────────────────────┘
```

### Test Categories

#### 1. Unit Tests
- **Purpose**: Test individual components in isolation
- **Examples**:
  - Environment validation functions
  - Logger functionality
  - Utility functions
  - Data transformations
- **Execution**: Fast (< 1 second)
- **Coverage Target**: > 80%

#### 2. Integration Tests
- **Purpose**: Test component interactions
- **Examples**:
  - Service connectivity
  - Cross-DB operations
  - API contract compliance
  - Provider integration
- **Execution**: Medium (1-10 seconds)
- **Dependencies**: May require services

#### 3. CI/CD Tests
- **Purpose**: Validate CI/CD configuration
- **Examples**:
  - Health check configuration
  - Service dependencies
  - Output validation
  - Timeout values
- **Execution**: Fast (< 1 second)
- **Method**: Static analysis of config files

#### 4. Benchmark Tests
- **Purpose**: Performance and correctness validation
- **Examples**:
  - Latency measurements
  - Recall evaluation
  - Golden test validation
  - Cross-DB comparison
- **Execution**: Slow (minutes)
- **Dependencies**: All services required

---

## Monitoring and Observability

### Logging Levels

- **DEBUG**: Detailed information for diagnosing issues
- **INFO**: General information about system operation
- **WARN**: Warning messages for potentially problematic situations
- **ERROR**: Error messages with exception details

### Key Metrics

#### Benchmark Metrics
- `indexed_points`: Number of vectors successfully indexed
- `query_count`: Number of search queries executed
- `latency_ms.p50/p95/p99`: Search latency percentiles
- `throughput`: Operations per second
- `recall@k`: Recall accuracy for top-k results

#### Service Metrics
- `startup_time`: Time for service to become healthy
- `health_check_failures`: Number of failed health checks
- `request_success_rate`: Percentage of successful requests
- `error_rate`: Percentage of failed operations

#### CI/CD Metrics
- `pipeline_duration`: Total CI/CD execution time
- `validation_failures`: Pre-flight check failures
- `artifact_generation_success`: Output file generation rate
- `test_pass_rate`: Percentage of passing tests

### Log Files

- `assets/bench/server.log`: API service request logs
- `assets/bench/bench.log`: QA container execution logs
- `assets/bench/progress.log`: Benchmark progress tracking
- `tests/bench/*.log`: Component-specific logs (if enabled)

### Artifact Files

- `assets/bench/bench_report.json`: Benchmark results
- `assets/bench/recall_report.json`: Recall evaluation results
- `assets/bench/compare.json`: Cross-DB comparison results
- `assets/bench/compare.md`: Human-readable comparison
- `assets/golden/*.json`: Golden test data and proofs

---

## Best Practices

### 1. Error Handling
- Always use structured logging for errors
- Include context (component, operation) in error messages
- Capture full exception details with tracebacks
- Use appropriate error codes for different failure types

### 2. Configuration Management
- Use environment variables for all configuration
- Validate all env vars at startup (pre-flight check)
- Provide sensible defaults for optional settings
- Document all configuration options

### 3. Service Management
- Always wait for service health before use
- Implement retry logic with exponential backoff
- Set appropriate timeouts for all operations
- Clean up resources on shutdown

### 4. Testing
- Write tests for all validation logic
- Test both success and failure paths
- Use mocks for external dependencies when appropriate
- Maintain high test coverage (> 80%)

### 5. Monitoring
- Log all significant operations
- Include timing information for performance analysis
- Use structured logging for machine parseability
- Generate comprehensive reports with all metrics

---

## Maintenance Guide

### Adding a New Service

1. Add service to `docker-compose.ci.yml`
2. Configure health check
3. Add to QA service dependencies
4. Update CI workflow verification
5. Add tests in `test_ci_service_health.py`
6. Update documentation

### Adding a New Environment Variable

1. Add validation in `env_validator.py`
2. Add test in `test_env_validator.py`
3. Add to `preflight_check.py` validation
4. Document in `ENVIRONMENT_VARIABLES.md`
5. Update default in docker-compose if needed

### Adding a New Benchmark

1. Create benchmark script in `tests/bench/`
2. Add to QA container command in docker-compose
3. Add output validation in CI workflow
4. Add artifact upload in CI workflow
5. Document in `README_bench.md`

### Troubleshooting

For detailed troubleshooting procedures, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

For environment variable reference, see [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md).

---

## Future Improvements

### Planned Enhancements
- [ ] Distributed tracing integration
- [ ] Metrics export to Prometheus
- [ ] Real-time dashboard for benchmarks
- [ ] Automated performance regression detection
- [ ] Multi-region deployment support
- [ ] Benchmark result caching
- [ ] Historical trend analysis
- [ ] Alert system for CI failures

### Under Consideration
- Additional vector database integrations (Pinecone, Weaviate, etc.)
- Multi-language client support
- Advanced caching strategies
- Query optimization recommendations
- Automated tuning suggestions
