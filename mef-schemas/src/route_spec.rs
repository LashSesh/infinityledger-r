//! RouteSpec - S7 route specification with 7-slot permutation

use serde::{Deserialize, Serialize};

/// RouteSpec represents a permutation of the 7 operators in S7 space
/// The permutation space has 7! = 5040 possible routes
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RouteSpec {
    /// The route identifier (content-addressed)
    pub route_id: String,
    
    /// The 7-slot permutation of operators [0..7)
    pub permutation: Vec<usize>,
    
    /// Mesh metrics: betti number, spectral gap, persistence
    pub mesh_score: f64,
}

impl RouteSpec {
    /// Create a new RouteSpec with validation
    pub fn new(route_id: String, permutation: Vec<usize>, mesh_score: f64) -> crate::Result<Self> {
        // Validate permutation is a valid 7-element permutation
        if permutation.len() != 7 {
            return Err(crate::SchemaError::InvalidRoute(
                format!("Permutation must have exactly 7 elements, got {}", permutation.len())
            ));
        }
        
        // Check all elements are unique and in range [0..7)
        let mut seen = vec![false; 7];
        for &idx in &permutation {
            if idx >= 7 {
                return Err(crate::SchemaError::InvalidRoute(
                    format!("Invalid permutation index: {}", idx)
                ));
            }
            if seen[idx] {
                return Err(crate::SchemaError::InvalidRoute(
                    format!("Duplicate permutation index: {}", idx)
                ));
            }
            seen[idx] = true;
        }
        
        Ok(Self {
            route_id,
            permutation,
            mesh_score,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_valid_route_spec() {
        let route = RouteSpec::new(
            "route_001".to_string(),
            vec![0, 1, 2, 3, 4, 5, 6],
            0.75,
        );
        assert!(route.is_ok());
    }

    #[test]
    fn test_invalid_permutation_length() {
        let route = RouteSpec::new(
            "route_002".to_string(),
            vec![0, 1, 2],
            0.5,
        );
        assert!(route.is_err());
    }

    #[test]
    fn test_duplicate_index() {
        let route = RouteSpec::new(
            "route_003".to_string(),
            vec![0, 1, 2, 2, 4, 5, 6],
            0.5,
        );
        assert!(route.is_err());
    }
}
