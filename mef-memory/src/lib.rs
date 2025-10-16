//! # MEF Memory Module
//!
//! This module provides vector memory indexing and similarity search for the
//! MEF Knowledge Engine extension (SPEC-006).
//!
//! ## Architecture
//!
//! This is an ADD-ONLY extension that provides vector database abstraction without
//! modifying core components. It includes:
//!
//! - **Index abstraction**: Pluggable vector database backends (FAISS, HNSW, etc.)
//! - **Upsert operations**: Store 8D normalized vectors with metadata
//! - **Similarity search**: Cosine similarity queries with filtering
//! - **No-op mode**: Complete functionality disabled when `memory.enabled=false`
//!
//! ## Integration Points
//!
//! - Consumes `MemoryItem` from `mef-schemas`
//! - Uses `Vector8Builder` from `mef-knowledge` for vector construction
//! - Does NOT depend on or modify core MEF pipeline
//!
//! ## Feature Flags
//!
//! All functionality respects the `memory.enabled` config flag. When disabled,
//! all operations return empty results without error.

pub mod index;
pub mod operations;
pub mod backends;

// Re-exports for convenience
pub use index::{MemoryIndex, MemoryConfig};
pub use operations::{UpsertRequest, SearchRequest, SearchResult};

/// Module version
pub const VERSION: &str = "1.0.0";
