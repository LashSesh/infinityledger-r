/*!
 * MEF Domains - Domain-Layer Extension for MEF-Core
 * 
 * Implements Resonit/Resonat structures, MeshHolo triangulation,
 * and cross-domain homeomorphism with Metatron Cube integration.
 * 
 * This layer enables domain-specific transformations while maintaining
 * the domain-agnostic nature of the core pipeline.
 */

pub mod resonit;
pub mod resonat;
pub mod infogenome;
pub mod meshholo;
pub mod adapter;
pub mod domain_layer;
pub mod xswap;

// Re-export main types
pub use resonit::{Resonit, Sigma};
pub use resonat::{Resonat, ResonatMetrics};
pub use infogenome::{Infogene, Infogenome};
pub use meshholo::{MeshHolo, VertexData, EdgeData, TopologicalInvariants};
pub use adapter::{DomainAdapter, TextDomainAdapter, SignalDomainAdapter};
pub use domain_layer::{
    DomainLayer, DomainMetrics, DomainProcessingResult, 
    GateValidation, CrossDomainResult
};
pub use xswap::{Xswap, AlignmentArtifacts};

