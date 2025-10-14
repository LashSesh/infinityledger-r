//! MEF-Core Spiral Module
//!
//! 5D spiral snapshot and storage implementation with deterministic addressing.
//!
//! Migrated from: MEF-Core_v1.0/src/spiral/

pub mod snapshot;

pub use snapshot::{
    Metrics, Payload, Sigma, Snapshot, SpiralConfig, SpiralSnapshot,
};
