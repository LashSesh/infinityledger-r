//! # MEF Knowledge Module
//!
//! This module provides knowledge derivation, projection, and validation for the
//! MEF Knowledge Engine extension (SPEC-006).
//!
//! ## Architecture
//!
//! This is an ADD-ONLY extension layer that integrates with the core MEF system
//! without modifying existing components. It provides:
//!
//! - **Metric computation**: Build 8D weighted vectors from 5D spiral + 3D spectral
//! - **Knowledge derivation**: Bind TICs with routes and seed paths
//! - **Projection**: Transform knowledge into queryable representations
//! - **Validation**: Verify knowledge integrity and provenance
//!
//! ## Integration Points
//!
//! - Reads from `mef-spiral` for 5D coordinates and spectral signatures
//! - Reads from `mef-ledger` for TIC retrieval
//! - Updates `mef-hdag` for knowledge graph relationships
//! - Does NOT modify core solve-coagula iteration or gate logic
//!
//! ## Feature Flags
//!
//! All functionality in this module respects the `knowledge.enabled` config flag.
//! When disabled, all operations are no-ops.

pub mod metric;
pub mod inference;
pub mod derivation;
pub mod primitives;

// Re-exports for convenience
pub use metric::Vector8Builder;
pub use inference::{KnowledgeInference, ProjectionMode};
pub use derivation::KnowledgeDerivation;
pub use primitives::{canonical_json, compute_mef_id, compute_content_hash};

/// Module version
pub const VERSION: &str = "1.0.0";
