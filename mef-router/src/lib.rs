//! MEF Router - Metatron S7 route selection
//! 
//! This module provides:
//! - Complete S7 permutation space (7! = 5040 routes)
//! - Deterministic route selection via hash + mesh scoring
//! - Mesh metric computation: J(m) = 0.10·betti + 0.70·λ_gap + 0.20·persistence
//! - MetatronAdapter with in-process and service modes

pub mod s7_space;
pub mod route_selection;
pub mod mesh_metrics;
pub mod adapter;
pub mod s7;
pub mod scoring;

pub use s7_space::generate_s7_permutations;
pub use route_selection::select_route;
pub use mesh_metrics::compute_mesh_score;
pub use adapter::{MetatronAdapter, AdapterMode};
pub use s7::{generate_permutations, select_route as select_route_v2};
pub use scoring::{mesh_score, extract_mesh_metrics};

#[derive(Debug, thiserror::Error)]
pub enum RouterError {
    #[error("Invalid metrics: {0}")]
    InvalidMetrics(String),
    
    #[error("Route selection error: {0}")]
    Selection(String),
    
    #[error("Adapter error: {0}")]
    Adapter(String),
}

pub type Result<T> = std::result::Result<T, RouterError>;
