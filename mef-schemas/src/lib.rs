//! # MEF Schemas Module
//!
//! This module provides JSON schema definitions and Rust type representations
//! for the MEF Knowledge Engine extension (SPEC-006).
//!
//! ## Architecture
//!
//! This is part of the extension layer and does NOT modify core system schemas.
//! All schemas here are additive and follow the ADD-ONLY principle.
//!
//! ## Schemas Provided
//!
//! - `RouteSpec`: Metatron S7 route specification
//! - `MemoryItem`: Vector memory storage item (8D weighted vectors)
//! - `KnowledgeObject`: Derived knowledge with TIC binding
//! - `SpiralSnapshot`: 5D spiral coordinates with spectral signature (extended)
//! - `TicExtended`: TIC with gate proofs (extended)
//! - `MefBlockExtended`: Block with route and proof bundle (extended)
//! - `MerkabaGateEvent`: Gate decision event
//!
//! ## Feature Flags
//!
//! - `validation`: Enable JSON schema validation (optional)

pub mod route_spec;
pub mod memory_item;
pub mod knowledge;
pub mod gate;

// Re-exports for convenience
pub use route_spec::{RouteSpec, OperatorSlot};
pub use memory_item::{MemoryItem, SpectralSignature, PorStatus};
pub use knowledge::{KnowledgeObject, TicReference, RouteReference, KnowledgeContext};
pub use gate::{MerkabaGateEvent, GateChecks, GateDecision};

/// Extension version following SPEC-006
pub const EXTENSION_VERSION: &str = "1.0.0-expansion-1.4";
