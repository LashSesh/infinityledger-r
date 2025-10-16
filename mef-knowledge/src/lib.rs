//! MEF Knowledge - Knowledge processing and derivation
//! 
//! This module provides:
//! - Canonical JSON serialization (deterministic, stable key order)
//! - Content-addressed knowledge IDs via SHA256 hashing
//! - HD-style seed derivation using HMAC-SHA256
//! - 8D vector construction from 5D spiral + 3D spectral features
//! - Knowledge inference and projection engine (scaffold)

pub mod canonical;
pub mod content_address;
pub mod seed_derivation;
pub mod vector8;
pub mod inference;

pub use canonical::canonical_json;
pub use content_address::compute_mef_id;
pub use seed_derivation::derive_seed;
pub use vector8::{Vector8Builder, Vector8Config};

#[derive(Debug, thiserror::Error)]
pub enum KnowledgeError {
    #[error("Canonical JSON error: {0}")]
    Canonical(String),
    
    #[error("Content addressing error: {0}")]
    ContentAddress(String),
    
    #[error("Seed derivation error: {0}")]
    SeedDerivation(String),
    
    #[error("Vector construction error: {0}")]
    VectorConstruction(String),
    
    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, KnowledgeError>;
