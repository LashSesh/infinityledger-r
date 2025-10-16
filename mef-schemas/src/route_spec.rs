//! # Route Specification Schema
//!
//! Defines the structure for Metatron S7 routing specifications.
//!
//! ## SPEC-006 Reference
//!
//! From Part 3, Section 1.5:
//! - 7-slot permutation over {DK, SW, PI, WT, RES1, ADAPTER, RES2}
//! - Sigma: permutation indices [1..7]
//! - Score: mesh metric J(m) = 0.10*b + 0.70*λ + 0.20*p

use serde::{Deserialize, Serialize};

/// Operator slot types in the Solve-Coagula route
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OperatorSlot {
    /// DoubleKick operator (mandatory)
    DK,
    /// Soft-Threshold Sweep operator (mandatory)
    SW,
    /// Path Invariance projection (mandatory)
    PI,
    /// Weight Transfer operator (mandatory)
    WT,
    /// Reserved slot 1 (optional/no-op by default)
    RES1,
    /// Adapter slot (optional/no-op by default)
    ADAPTER,
    /// Reserved slot 2 (optional/no-op by default)
    RES2,
}

/// Route specification for Metatron S7 router
///
/// Defines a 7-slot permutation of operators for the Solve-Coagula iteration.
/// The route is deterministically selected based on seed and mesh metrics.
///
/// ## JSON Schema
///
/// ```json
/// {
///   "route_id": "a1b2c3d4e5f6g7h8",
///   "sigma": [3, 1, 4, 2, 5, 7, 6],
///   "permutation": ["PI", "DK", "WT", "SW", "RES1", "RES2", "ADAPTER"],
///   "score": 0.842
/// }
/// ```
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RouteSpec {
    /// Unique route identifier (deterministic hash)
    pub route_id: String,
    
    /// Permutation indices [1..7] for the 7 slots
    pub sigma: Vec<u8>,
    
    /// Ordered list of operator slots
    pub permutation: Vec<OperatorSlot>,
    
    /// Mesh metric score J(m) used for route selection
    pub score: f64,
}

impl RouteSpec {
    /// Create a new route specification
    ///
    /// # Arguments
    ///
    /// * `route_id` - Unique identifier (typically a hash)
    /// * `sigma` - Permutation indices [1..7]
    /// * `permutation` - Ordered operator slots
    /// * `score` - Mesh metric score
    ///
    /// # Panics
    ///
    /// Panics if sigma or permutation length is not exactly 7
    pub fn new(route_id: String, sigma: Vec<u8>, permutation: Vec<OperatorSlot>, score: f64) -> Self {
        assert_eq!(sigma.len(), 7, "Sigma must have exactly 7 elements");
        assert_eq!(permutation.len(), 7, "Permutation must have exactly 7 elements");
        assert!(sigma.iter().all(|&x| x >= 1 && x <= 7), "Sigma values must be in [1..7]");
        
        Self {
            route_id,
            sigma,
            permutation,
            score,
        }
    }
    
    /// Validate the route specification
    pub fn validate(&self) -> Result<(), String> {
        if self.sigma.len() != 7 {
            return Err("Sigma must have exactly 7 elements".to_string());
        }
        if self.permutation.len() != 7 {
            return Err("Permutation must have exactly 7 elements".to_string());
        }
        if !self.sigma.iter().all(|&x| x >= 1 && x <= 7) {
            return Err("Sigma values must be in [1..7]".to_string());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_route_spec_creation() {
        let route = RouteSpec::new(
            "test_route_123".to_string(),
            vec![3, 1, 4, 2, 5, 7, 6],
            vec![
                OperatorSlot::PI,
                OperatorSlot::DK,
                OperatorSlot::WT,
                OperatorSlot::SW,
                OperatorSlot::RES1,
                OperatorSlot::RES2,
                OperatorSlot::ADAPTER,
            ],
            0.842,
        );
        
        assert_eq!(route.route_id, "test_route_123");
        assert_eq!(route.sigma.len(), 7);
        assert_eq!(route.permutation.len(), 7);
        assert!(route.validate().is_ok());
    }

    #[test]
    fn test_route_spec_serialization() {
        let route = RouteSpec::new(
            "test".to_string(),
            vec![1, 2, 3, 4, 5, 6, 7],
            vec![
                OperatorSlot::DK,
                OperatorSlot::SW,
                OperatorSlot::PI,
                OperatorSlot::WT,
                OperatorSlot::RES1,
                OperatorSlot::ADAPTER,
                OperatorSlot::RES2,
            ],
            0.5,
        );
        
        let json = serde_json::to_string(&route).unwrap();
        let deserialized: RouteSpec = serde_json::from_str(&json).unwrap();
        
        assert_eq!(route, deserialized);
    }
}
