# Infinity Ledger (MEF-Core)

[![CI/CD](https://github.com/LashSesh/infinityledger/workflows/Rust%20CI/CD/badge.svg)](https://github.com/LashSesh/infinityledger/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Infinity Ledger** is a high-performance, enterprise-grade implementation of the MEF-Core (Mandorla Eigenstate Fractals) system, written entirely in Rust for maximum performance, safety, and reliability.

## 🦀 Modern Rust Implementation

This project represents a complete Rust reimplementation of the MEF-Core system, featuring:

- **🔒 Type-Safe**: Leveraging Rust's type system for compile-time guarantees
- **⚡ High Performance**: Zero-cost abstractions and efficient memory management
- **🔐 Secure**: Memory-safe and thread-safe by default
- **🌐 Concurrent**: Built on Tokio for async I/O and parallel processing
- **📊 Production-Ready**: Comprehensive testing, benchmarking, and monitoring

## 🏗️ Architecture

### Core Modules

| Module | Description | Status |
|--------|-------------|--------|
| **mef-core** | Core MEF pipeline and fractal processing | ✅ |
| **mef-spiral** | Spiral snapshot system with deterministic hashing | ✅ |
| **mef-ledger** | Hash-chained immutable ledger for TICs | ✅ |
| **mef-hdag** | Hierarchical Directed Acyclic Graph | ✅ |
| **mef-tic** | Temporal Information Crystals (TIC) processing | ✅ |
| **mef-coupling** | Spiral coupling engine | ✅ |
| **mef-topology** | Metatron router and topological operations | ✅ |
| **mef-domains** | Domain-specific processing and resonance analysis | ✅ |
| **mef-vector-db** | Vector database abstraction (HNSW, IVF-PQ) | ✅ |
| **mef-storage** | Persistent storage with S3 support | ✅ |
| **mef-solvecoagula** | XSwap and quantum processing | ✅ |
| **mef-audit** | Merkaba gate and audit logging | ✅ |
| **mef-ingestion** | Data ingestion pipeline | ✅ |
| **mef-specs** | Acquisition specifications | ✅ |
| **mef-acquisition** | Data acquisition layer | ✅ |

### Applications

| Application | Description |
|-------------|-------------|
| **mef-api** | HTTP REST API server (Axum) |
| **mef-cli** | Command-line interface |
| **mef-bench** | Cross-database benchmarking tool |
| **mef-benchmarks** | Performance benchmarks (Criterion) |

## 🚀 Quick Start

### Prerequisites

- Rust 1.70+ (install from [rustup.rs](https://rustup.rs))
- Cargo (comes with Rust)

### Building

```bash
# Clone the repository
git clone https://github.com/LashSesh/infinityledger.git
cd infinityledger

# Build all packages
cargo build --release

# Run tests
cargo test --workspace
```

### Running the API Server

```bash
# Start the API server
cargo run --release --package mef-api --bin mef-api

# In another terminal, test the health endpoint
curl http://localhost:8000/healthz
```

### Using the CLI

```bash
# Build the CLI
cargo build --release --package mef-cli

# Run CLI commands
./target/release/mef --help
```

### Running Cross-Database Benchmarks

```bash
# Build the benchmark tool
cargo build --release --package mef-bench

# Run benchmarks (requires services to be running)
./target/release/cross-db-bench faiss mef qdrant

# With custom configuration
BENCH_NUM_VECTORS=50000 \
BENCH_NUM_QUERIES=100 \
BENCH_DIMENSION=128 \
BENCH_BATCH_SIZE=5000 \
./target/release/cross-db-bench faiss mef
```

## 🧪 Testing

### Unit Tests

```bash
# Run all unit tests
cargo test --workspace --lib

# Run specific package tests
cargo test --package mef-ledger
cargo test --package mef-spiral
```

### Integration Tests

```bash
# Run integration tests
cargo test --workspace --test '*'

# Run with output
cargo test --workspace --test '*' -- --nocapture
```

### Benchmarks

```bash
# Run criterion benchmarks
cargo bench --package mef-benchmarks

# View results
open target/criterion/report/index.html
```

## 📊 Key Features

### Deterministic Hashing

The ledger implements deterministic hash computation with:
- Canonical JSON serialization (sorted keys)
- Normalized floating-point representation
- Round-trip safe f64 handling
- Golden tests for hash consistency

### Hash-Chained Ledger

- Immutable append-only blockchain
- SHA-256 hash chaining
- Integrity verification at any point
- Compact TIC representation

### Spiral Snapshots

- Deterministic snapshot creation
- Configurable parameters (N, phi, rotation)
- Persistent storage and retrieval
- Coordinates in 5D fractal space

### Vector Database Abstraction

- Multiple provider support (FAISS, Qdrant, Milvus, etc.)
- HNSW and IVF-PQ indexing
- Cosine similarity search
- Batch operations

### Cross-Database Benchmarking

- Automated performance comparison
- Multiple vector databases
- Configurable workloads
- Detailed metrics (latency, recall, QPS)

## 🐳 Docker Support

```bash
# Build Docker image
docker build -t infinityledger .

# Run with docker-compose
docker-compose -f docker-compose.rust.yml up

# Run benchmarks
docker-compose -f docker-compose.bench.yml up
```

## 📚 Documentation

- [Rust Build Guide](./RUST_BUILD_GUIDE.md) - Detailed build instructions
- [Cross-DB Benchmark Guide](./CROSS_DB_BENCHMARK_GUIDE.md) - Benchmarking documentation
- [Deployment Guide](./DEPLOYMENT.md) - Production deployment
- [Migration History](./MIGRATION.md) - Python to Rust migration notes

### API Documentation

Generate and view API documentation:

```bash
cargo doc --workspace --no-deps --open
```

## 🔧 Development

### Project Structure

```
infinityledger/
├── mef-core/          # Core MEF pipeline
├── mef-spiral/        # Spiral snapshots
├── mef-ledger/        # Hash-chained ledger
├── mef-api/           # HTTP API server
├── mef-cli/           # CLI application
├── mef-bench/         # Benchmarking tools
├── mef-benchmarks/    # Performance benchmarks
└── [other modules]/   # Additional MEF components
```

### Code Quality

```bash
# Format code
cargo fmt --all

# Run clippy
cargo clippy --all-targets --all-features -- -D warnings

# Security audit
cargo audit
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`cargo test --workspace`)
5. Format code (`cargo fmt --all`)
6. Run clippy (`cargo clippy --all-targets`)
7. Commit changes (`git commit -m 'Add amazing feature'`)
8. Push to branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- [GitHub Repository](https://github.com/LashSesh/infinityledger)
- [CI/CD Pipeline](https://github.com/LashSesh/infinityledger/actions)
- [Issue Tracker](https://github.com/LashSesh/infinityledger/issues)

## 📊 CI/CD Status

The project uses GitHub Actions for continuous integration:

- ✅ **Lint and Format**: Code quality checks with rustfmt and clippy
- ✅ **Build and Test**: Comprehensive test suite across all modules  
- ✅ **Integration Tests**: End-to-end testing with services
- ✅ **Benchmarks**: Performance regression testing
- ✅ **Cross-DB Benchmarks**: Multi-database performance comparison
- ✅ **Security Audit**: Dependency vulnerability scanning
- ✅ **Docker Build**: Container image creation

## 🆘 Support

For questions, issues, or feature requests, please [open an issue](https://github.com/LashSesh/infinityledger/issues) on GitHub.

---

**Built with ❤️ in Rust** | **Last Updated**: October 2025 | **Version**: 1.0.0
