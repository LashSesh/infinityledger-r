//! # Memory Item Schema
//!
//! Defines the structure for 8D weighted vector storage in the memory index.
//!
//! ## SPEC-006 Reference
//!
//! From Part 2, Section 2.1:
//! - z' = [w1*x1, ..., w5*x5, wψ*ψ, wρ*ρ, wω*ω] ∈ R^8
//! - ẑ = z' / ||z'||₂ (normalized)
//!
//! From Part 3, Section 1.6:
//! - Cosine similarity on ẑ is equivalent to L2 distance

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Spectral signature components (PoR features)
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpectralSignature {
    /// Mid-band ratio ψ = EM / (EL + EM + EH)
    pub psi: f64,
    
    /// Low/mid ratio ρ = EL / (EM + EH + ε)
    pub rho: f64,
    
    /// High-band ratio ω = EH / (EL + EM + ε)
    pub omega: f64,
}

/// Proof of Resonance validation status
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum PorStatus {
    /// PoR validation passed
    Valid,
    
    /// PoR validation failed
    Invalid,
}

/// Memory item for vector index storage
///
/// Represents a normalized 8D weighted vector combining 5D spatial coordinates
/// with 3D spectral features for similarity search.
///
/// ## JSON Schema
///
/// ```json
/// {
///   "id": "MEF-a8b3",
///   "vector8": [0.2231, 0.0, 0.1076, 0.0981, 0.5348, 0.1180, -0.2144, 0.7382],
///   "sigma": {"psi": 0.31, "rho": 0.28, "omega": 0.41},
///   "por": "valid",
///   "tic_id": "TIC-9f2a",
///   "metadata": {"domain": "text"}
/// }
/// ```
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MemoryItem {
    /// Unique memory item identifier
    pub id: String,
    
    /// Normalized 8D vector ẑ ∈ R^8 with ||ẑ||₂ = 1
    pub vector8: Vec<f64>,
    
    /// Spectral signature components
    pub sigma: SpectralSignature,
    
    /// Proof of Resonance status
    pub por: PorStatus,
    
    /// Associated TIC identifier
    pub tic_id: String,
    
    /// Optional metadata (domain, timestamps, etc.)
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl MemoryItem {
    /// Create a new memory item
    ///
    /// # Arguments
    ///
    /// * `id` - Unique identifier
    /// * `vector8` - 8D normalized vector
    /// * `sigma` - Spectral signature
    /// * `por` - PoR status
    /// * `tic_id` - Associated TIC ID
    ///
    /// # Panics
    ///
    /// Panics if vector8 length is not exactly 8
    pub fn new(
        id: String,
        vector8: Vec<f64>,
        sigma: SpectralSignature,
        por: PorStatus,
        tic_id: String,
    ) -> Self {
        assert_eq!(vector8.len(), 8, "vector8 must have exactly 8 dimensions");
        
        Self {
            id,
            vector8,
            sigma,
            por,
            tic_id,
            metadata: HashMap::new(),
        }
    }
    
    /// Add metadata key-value pair
    pub fn with_metadata(mut self, key: String, value: serde_json::Value) -> Self {
        self.metadata.insert(key, value);
        self
    }
    
    /// Validate the memory item
    pub fn validate(&self) -> Result<(), String> {
        if self.vector8.len() != 8 {
            return Err("vector8 must have exactly 8 dimensions".to_string());
        }
        
        // Check normalization (approximately unit length)
        let norm_squared: f64 = self.vector8.iter().map(|x| x * x).sum();
        if (norm_squared - 1.0).abs() > 1e-6 {
            return Err(format!(
                "vector8 must be normalized (||v||² = {:.6}, expected ~1.0)",
                norm_squared
            ));
        }
        
        Ok(())
    }
    
    /// Compute cosine similarity with another memory item
    ///
    /// For normalized vectors: cos(ẑ, ŷ) = 1 - ||ẑ - ŷ||²/2
    pub fn cosine_similarity(&self, other: &MemoryItem) -> f64 {
        let dot_product: f64 = self.vector8
            .iter()
            .zip(&other.vector8)
            .map(|(a, b)| a * b)
            .sum();
        
        dot_product
    }
    
    /// Compute L2 distance to another memory item
    pub fn l2_distance(&self, other: &MemoryItem) -> f64 {
        let squared_diff: f64 = self.vector8
            .iter()
            .zip(&other.vector8)
            .map(|(a, b)| (a - b).powi(2))
            .sum();
        
        squared_diff.sqrt()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_memory_item_creation() {
        let item = MemoryItem::new(
            "MEF-test".to_string(),
            vec![0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0],
            SpectralSignature {
                psi: 0.3,
                rho: 0.3,
                omega: 0.4,
            },
            PorStatus::Valid,
            "TIC-123".to_string(),
        );
        
        assert_eq!(item.vector8.len(), 8);
    }

    #[test]
    fn test_cosine_l2_equivalence() {
        // For normalized vectors: cos(ẑ, ŷ) = 1 - ||ẑ - ŷ||²/2
        let v1 = vec![1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        let v2 = vec![0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0];
        
        let item1 = MemoryItem::new(
            "1".to_string(),
            v1,
            SpectralSignature { psi: 0.3, rho: 0.3, omega: 0.4 },
            PorStatus::Valid,
            "TIC-1".to_string(),
        );
        
        let item2 = MemoryItem::new(
            "2".to_string(),
            v2,
            SpectralSignature { psi: 0.3, rho: 0.3, omega: 0.4 },
            PorStatus::Valid,
            "TIC-2".to_string(),
        );
        
        let cos = item1.cosine_similarity(&item2);
        let l2 = item1.l2_distance(&item2);
        
        // cos(ẑ, ŷ) = 1 - ||ẑ - ŷ||²/2
        let expected_cos = 1.0 - (l2 * l2) / 2.0;
        
        assert!((cos - expected_cos).abs() < 1e-9);
    }
}
