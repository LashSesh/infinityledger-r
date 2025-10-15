/*! 
 * MEF Vector DB - Vector database abstraction and proof registry
 * 
 * This module provides:
 * - Index management and persistence
 * - Merkle-tree based proof registry
 * - Vector database provider abstraction
 * - S3-backed manifest storage
 */

mod manifest_store;
mod proof_registry;

pub use manifest_store::{ManifestStore, Manifest, PersistenceConfig};
pub use proof_registry::{ProofRegistry, MembershipProof, ProofError};

// Type aliases for NumPy compatibility
/// Float32 type (equivalent to np.float32)
pub type F32 = f32;

/// Unsigned 32-bit integer type (equivalent to np.uint32)
pub type U32 = u32;
