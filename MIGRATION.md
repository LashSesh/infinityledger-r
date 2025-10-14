# MEF-Core Python to Rust Migration Documentation

## Overview

This document tracks the deterministic migration of the MEF-Core (Mandorla Eigenstate Fractals) repository from Python to Rust.

**Migration Start Date**: 2025-10-14  
**Python Codebase**: 154 files, ~15,000 lines of code  
**Target**: Complete Rust reimplementation with identical functionality

## Migration Principles

1. **Deterministic**: Same inputs must produce identical outputs in both Python and Rust
2. **Traceable**: Each migrated file gets its own commit referencing the original
3. **Documented**: All transformations, assumptions, and decisions documented here
4. **Tested**: Rust tests validate behavior matches Python implementation
5. **Idiomatic**: Use Rust best practices and idioms where appropriate

## Project Structure Mapping

### Python → Rust Workspace

The Python monolithic structure has been reorganized into a Rust workspace with multiple crates:

```
MEF-Core_v1.0/src/          → Rust workspace with multiple crates
├── spiral/                 → mef-spiral crate
├── ledger/                 → mef-ledger crate  
├── hdag/                   → mef-hdag crate
├── ingestion/              → mef-ingestion crate
├── solvecoagula/           → mef-solvecoagula crate
├── tic/                    → mef-tic crate
├── coupling/               → mef-coupling crate
├── audit/                  → mef-audit crate
├── api/                    → mef-api crate
├── cli/                    → mef-cli crate
└── (other modules)         → mef-core crate (core utilities)
```

### Rationale
- **Modularity**: Separate crates allow independent compilation and versioning
- **Clarity**: Clear dependency boundaries between components
- **Testing**: Each crate can be tested independently
- **Reusability**: Components can be used separately if needed

## Dependency Mapping

### Python Dependencies → Rust Equivalents

| Python Library | Rust Equivalent | Notes |
|----------------|-----------------|-------|
| numpy | ndarray | Core numeric arrays |
| scipy | ndarray + custom | No direct equivalent, implement needed algorithms |
| fastapi | axum / actix-web | Modern async web framework |
| uvicorn | tokio + axum | Built-in async runtime |
| pydantic | serde | Serialization/deserialization |
| click | clap | CLI argument parsing |
| pytest | built-in tests | Rust native test framework |
| hashlib | sha2 | Cryptographic hashing |
| boto3 | aws-sdk-rust | AWS SDK |
| grpcio | tonic | gRPC framework |
| jsonschema | schemars / jsonschema | JSON schema validation |
| networkx | petgraph | Graph data structures |
| pymilvus | milvus-sdk-rust | Vector DB client (if available) |
| qdrant-client | qdrant-client | Vector DB client |
| weaviate-client | TBD | May need custom implementation |

### Dependencies Not Migrated

The following Python dependencies have no direct Rust equivalent or are not needed:
- **environs**: Environment variable handling (use std::env)
- **marshmallow**: Schema validation (use serde)
- **aiofiles**: Async file I/O (use tokio::fs)
- **websockets**: WebSocket support (use axum's WebSocket support)
- **python-multipart**: Multipart form data (use axum's built-in support)

## Key Transformations

### 1. Type System

**Python (dynamic typing)**:
```python
def compute_coordinates(self, theta: float, seed: str) -> List[float]:
    coords = [
        r_mod * np.cos(theta),
        r_mod * np.sin(theta),
        self.a * theta,
        self.b * np.sin(self.k * theta),
        self.c * np.cos(self.k * theta)
    ]
    return coords
```

**Rust (static typing)**:
```rust
fn compute_coordinates(&self, theta: f64, seed: &str) -> Vec<f64> {
    let coords = vec![
        r_mod * theta.cos(),
        r_mod * theta.sin(),
        self.a * theta,
        self.b * (self.k * theta).sin(),
        self.c * (self.k * theta).cos(),
    ];
    coords
}
```

**Changes**:
- `List[float]` → `Vec<f64>`
- `str` → `&str` (borrowed string slice)
- `np.cos()` → `.cos()` (method on f64)

### 2. Error Handling

**Python (exceptions)**:
```python
def load_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
    file_path = self.store_path / f"{snapshot_id}.json"
    if not file_path.exists():
        raise FileNotFoundError(f"Snapshot {snapshot_id} not found")
    with open(file_path, 'r') as f:
        return json.load(f)
```

**Rust (Result type)**:
```rust
fn load_snapshot(&self, snapshot_id: &str) -> Result<Snapshot, Error> {
    let file_path = self.store_path.join(format!("{}.json", snapshot_id));
    if !file_path.exists() {
        return Err(Error::SnapshotNotFound(snapshot_id.to_string()));
    }
    let contents = std::fs::read_to_string(&file_path)?;
    let snapshot: Snapshot = serde_json::from_str(&contents)?;
    Ok(snapshot)
}
```

**Changes**:
- Exceptions → `Result<T, E>` return type
- `raise` → `return Err(...)`
- Automatic error propagation with `?` operator

### 3. Object-Oriented to Trait-Based

**Python (classes with inheritance)**:
```python
class BaseDriver(ABC):
    @abstractmethod
    def insert(self, vectors: np.ndarray, metadata: List[Dict]) -> None:
        pass
```

**Rust (traits)**:
```rust
pub trait VectorDriver {
    fn insert(&mut self, vectors: &Array2<f64>, metadata: &[Metadata]) -> Result<()>;
}
```

**Changes**:
- Abstract base classes → traits
- Multiple inheritance → trait composition
- Dynamic dispatch via trait objects when needed

### 4. Async/Await

**Python (asyncio)**:
```python
async def process_request(self, data: Dict) -> Dict:
    result = await self.compute_async(data)
    return result
```

**Rust (tokio)**:
```rust
async fn process_request(&self, data: &Data) -> Result<Response> {
    let result = self.compute_async(data).await?;
    Ok(result)
}
```

**Changes**:
- Same async/await syntax
- More explicit with Result handling
- Tokio runtime for async execution

### 5. Deterministic Hashing

**Python**:
```python
import hashlib
seed_hash = hashlib.sha256(seed.encode()).digest()
seed_mod = int.from_bytes(seed_hash[:4], 'big') / (2**32)
```

**Rust**:
```rust
use sha2::{Sha256, Digest};
let mut hasher = Sha256::new();
hasher.update(seed.as_bytes());
let seed_hash = hasher.finalize();
let seed_mod = u32::from_be_bytes(seed_hash[..4].try_into().unwrap()) as f64 / (2_u64.pow(32) as f64);
```

**Changes**:
- Same SHA256 algorithm ensures determinism
- Explicit byte order specification (big-endian)
- Type conversions are explicit

## Module-Specific Notes

### Spiral Module (mef-spiral)

**Files**:
- `snapshot.py` → `snapshot.rs`
- `storage.py` → `storage.rs`
- `proof_of_resonance.py` → `proof_of_resonance.rs`

**Key Challenges**:
- NumPy array operations → ndarray operations
- File I/O with JSON serialization
- Deterministic coordinate computation

**Solutions**:
- Use ndarray for N-dimensional arrays
- serde_json for JSON handling
- Maintain exact same mathematical formulas

### Ledger Module (mef-ledger)

**Files**:
- `mef_block.py` → `mef_block.rs`

**Key Challenges**:
- Hash chain integrity
- Block serialization format
- File-based persistence

**Solutions**:
- Use sha2 crate for SHA256
- Ensure JSON serialization order is consistent
- Use same file structure and naming

### HDAG Module (mef-hdag)

**Files**:
- `graph.py` → `graph.rs` ✅ MIGRATED

**Key Challenges**:
- Graph data structure implementation
- Topological ordering (Kahn's algorithm)
- Path invariance validation
- Cycle detection

**Solutions**:
- Custom HDAG implementation without external graph libraries
- Implement Kahn's algorithm for topological sorting
- DFS-based cycle detection
- HashMap-based adjacency list representation
- Maintain same node/edge representation as Python

**Status**: ✅ Complete (6 tests passing)

### Ingestion Module (mef-ingestion)

**Files**:
- `triton_core.py` → `triton_core.rs` ✅ MIGRATED
- `triton.py` → `triton.rs` (wrapper, can be skipped)

**Key Challenges**:
- SPEC-002 compliant payload normalization
- Multiple data type normalization
- Date string detection and conversion
- Deterministic vector generation

**Solutions**:
- Recursive normalization with serde_json::Value
- Regex-based date pattern matching
- SHA256-based deterministic hashing
- Key sorting for determinism

**Status**: ✅ Complete (7 tests passing)

### Audit Module (mef-audit)

**Files**:
- `logger.py` → `logger.rs` ✅ MIGRATED

**Key Challenges**:
- Event logging with buffering
- JSONL file format
- Event filtering and retrieval
- Report generation

**Solutions**:
- Custom logger implementation (not using Python's logging module)
- Buffered writes for performance
- Line-by-line JSONL reading for filtering
- HashMap-based aggregation for reports

**Status**: ✅ Complete (7 tests passing)

### Solve-Coagula Module (mef-solvecoagula)

**Files**:
- `operators.py` → `operators.rs`
- `doublekick.py` → `doublekick.rs`
- `pfadinvarianz.py` → `pfadinvarianz.rs`
- `sweep.py` → `sweep.rs`
- `weight_transfer.py` → `weight_transfer.rs`

**Key Challenges**:
- Complex numerical algorithms
- Fixpoint iteration
- Operator composition

**Solutions**:
- Port algorithms line-by-line
- Validate numerical precision
- Use f64 for consistency with Python floats

### TIC Module (mef-tic)

**Files**:
- `crystallizer.py` → `crystallizer.rs`

**Key Challenges**:
- Time window aggregation
- Invariant computation

**Solutions**:
- Use chrono for time handling
- Maintain same aggregation logic

### API Module (mef-api)

**Files**:
- `server.py` → `server.rs`
- `merkaba_api.py` → `merkaba_api.rs`
- Various endpoint handlers

**Key Challenges**:
- FastAPI → Axum migration
- Request/response handling
- Async endpoint handlers

**Solutions**:
- Use Axum for HTTP server
- Tonic for gRPC
- Maintain same API contracts

### CLI Module (mef-cli)

**Files**:
- `mef.py` → `main.rs`

**Key Challenges**:
- Command-line argument parsing
- Interactive prompts
- Output formatting

**Solutions**:
- Use clap for argument parsing
- Same command structure
- Match output format

## Testing Strategy

### Unit Tests

Each Rust module includes unit tests that validate:
1. **Determinism**: Same inputs produce same outputs as Python
2. **Edge Cases**: Handle boundary conditions correctly
3. **Error Handling**: Proper error propagation

### Integration Tests

Tests that span multiple modules:
1. **End-to-End Pipeline**: Data ingestion → Processing → Ledger
2. **API Contracts**: HTTP/gRPC endpoints match Python behavior
3. **Cross-Module**: Component interaction

### Validation Tests

Comparing Python and Rust outputs:
1. Generate test data with Python implementation
2. Process with Rust implementation
3. Assert outputs match (with appropriate floating-point tolerance)

## Migration Status

### Phase 1: Project Setup ✅
- [x] Created Cargo.toml workspace
- [x] Created MIGRATION.md
- [ ] Set up CI/CD for Rust builds

### Phase 2: Core Data Structures
- [ ] mef-spiral crate
- [ ] mef-ledger crate
- [ ] mef-hdag crate

### Phase 3: Processing Pipeline
- [ ] mef-ingestion crate
- [ ] mef-solvecoagula crate
- [ ] mef-tic crate
- [ ] mef-coupling crate

### Phase 4: Supporting Modules
- [ ] mef-audit crate
- [ ] mef-core crate (utilities)

### Phase 5: API & Services
- [ ] mef-api crate
- [ ] mef-cli crate

### Phase 6: Benchmark & Test Infrastructure
- [ ] Benchmark drivers
- [ ] Integration tests

### Phase 7: Documentation & Validation
- [ ] Update README
- [ ] Complete MIGRATION.md
- [ ] Final validation

## Known Limitations

1. **Vector DB Clients**: Some vector database clients may not have mature Rust equivalents
   - **Mitigation**: Use available crates or implement minimal HTTP clients

2. **SciPy Functions**: No direct equivalent for all SciPy functionality
   - **Mitigation**: Implement needed algorithms using ndarray

3. **Dynamic Python Features**: Some dynamic Python features don't translate directly
   - **Mitigation**: Use Rust's type system and traits for equivalent functionality

## Performance Expectations

Rust implementation should provide:
- **Faster Execution**: 2-10x speedup for computational tasks
- **Lower Memory**: More efficient memory usage
- **Better Concurrency**: Native async/await without GIL
- **Same Determinism**: Identical outputs for same inputs

## Validation Criteria

Migration is complete when:
1. ✅ All Python modules have Rust equivalents
2. ✅ All tests pass in Rust
3. ✅ Determinism validated (Python and Rust outputs match)
4. ✅ Documentation updated
5. ✅ CI/CD pipeline working
6. ✅ Performance benchmarks show improvement

## Commit Convention

Each migrated file follows this convention:
```
Migrate {module_name}.py to Rust

- Migrates MEF-Core_v1.0/src/{path}/{module_name}.py
- To: {crate_name}/src/{module_name}.rs
- Maintains identical functionality and determinism
- Tests included in {crate_name}/tests/
```

## References

- Original Python repository: LashSesh/infinityledger
- Python codebase: MEF-Core_v1.0/
- Migration branch: copilot/migrate-python-repo-to-rust

---

**Last Updated**: 2025-10-14  
**Status**: Phase 2 (Core Data Structures) - In Progress  
**Modules Migrated**: 5 of 76+ (6.6%)
