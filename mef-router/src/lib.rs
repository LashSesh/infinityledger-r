//! # MEF Router Module
//!
//! This module provides Metatron S7 routing for the MEF Knowledge Engine extension (SPEC-006).
//!
//! ## Architecture
//!
//! This is an ADD-ONLY extension that provides deterministic route selection without
//! modifying core solve-coagula logic. It includes:
//!
//! - **S7 permutation space**: Generate all 7! = 5040 possible routes
//! - **Mesh scoring**: Compute J(m) = 0.10*b + 0.70*λ + 0.20*p
//! - **Deterministic selection**: Hash-based route selection from seed and metrics
//! - **Adapter pattern**: Integrate with core topology without changes
//!
//! ## Integration Points
//!
//! - Reads mesh metrics from `mef-topology` (Metatron adapter)
//! - Provides route to `mef-solvecoagula` via configuration
//! - Does NOT modify core operator implementations (DK, SW, PI, WT)
//!
//! ## Mode
//!
//! Supports two modes via `router.mode` config:
//! - `inproc`: In-process adapter (default)
//! - `service`: External service call (future extension point)

pub mod s7;
pub mod adapter;
pub mod scoring;

// Re-exports for convenience
pub use s7::{generate_permutations, select_route};
pub use adapter::MetatronAdapter;
pub use scoring::mesh_score;

/// Module version
pub const VERSION: &str = "1.0.0";

/// Operator slot identifiers
pub const SLOTS: [&str; 7] = ["DK", "SW", "PI", "WT", "RES1", "ADAPTER", "RES2"];
