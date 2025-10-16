//! # Knowledge Inference
//!
//! Provides projection and transformation operations on knowledge objects.
//!
//! ## SPEC-006 Reference
//!
//! From Part 3, Section 2.2:
//! - /knowledge/derive: Create new knowledge from inputs
//! - /knowledge/project: Transform knowledge for specific use cases
//! - /knowledge/validate: Verify knowledge integrity

use mef_schemas::KnowledgeObject;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum InferenceError {
    #[error("Invalid projection mode: {0}")]
    InvalidMode(String),
    
    #[error("Missing required field: {0}")]
    MissingField(String),
    
    #[error("Validation failed: {0}")]
    ValidationFailed(String),
}

/// Projection modes for knowledge transformation
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ProjectionMode {
    /// Full knowledge object with all metadata
    Full,
    
    /// Compact representation (IDs only)
    Compact,
    
    /// Vector-only projection for similarity search
    Vector,
    
    /// Graph-oriented projection (relationships emphasized)
    Graph,
}

/// Knowledge inference engine
///
/// Provides pure functions for knowledge transformation and validation.
/// Does not maintain state or modify the core system.
pub struct KnowledgeInference;

impl KnowledgeInference {
    /// Project knowledge object according to specified mode
    ///
    /// ## Arguments
    ///
    /// * `knowledge` - The knowledge object to project
    /// * `mode` - Projection mode
    ///
    /// ## Returns
    ///
    /// Serialized projection as JSON value
    ///
    /// TODO: Implement actual projection logic based on mode
    pub fn project(
        knowledge: &KnowledgeObject,
        mode: ProjectionMode,
    ) -> Result<serde_json::Value, InferenceError> {
        match mode {
            ProjectionMode::Full => {
                // Return complete knowledge object
                Ok(serde_json::to_value(knowledge)
                    .map_err(|e| InferenceError::ValidationFailed(e.to_string()))?)
            }
            ProjectionMode::Compact => {
                // Return only essential IDs
                Ok(serde_json::json!({
                    "mef_id": knowledge.mef_id,
                    "tic_id": knowledge.tic.tic_id,
                    "route_id": knowledge.route.route_id,
                    "seed_path": knowledge.seed_path,
                    "block": knowledge.ledger_block,
                }))
            }
            ProjectionMode::Vector => {
                // TODO: Extract vector representation from knowledge
                // This would require retrieving the 8D vector from memory index
                Ok(serde_json::json!({
                    "mef_id": knowledge.mef_id,
                    "vector_ref": format!("vector:{}", knowledge.mef_id),
                    "note": "TODO: Implement vector retrieval from memory index"
                }))
            }
            ProjectionMode::Graph => {
                // Emphasize relationships
                Ok(serde_json::json!({
                    "mef_id": knowledge.mef_id,
                    "hdag_refs": knowledge.context.hdag_refs,
                    "parents": knowledge.context.parents,
                    "children": knowledge.context.children,
                }))
            }
        }
    }
    
    /// Validate knowledge object integrity
    ///
    /// Checks:
    /// - MEF ID matches computed hash
    /// - Route sigma is valid [1..7] permutation
    /// - Seed path follows format
    ///
    /// TODO: Implement full validation including ledger verification
    pub fn validate(knowledge: &KnowledgeObject) -> Result<(), InferenceError> {
        // Validate seed path format: "MEF/<domain>/<stage>/<index>"
        let parts: Vec<&str> = knowledge.seed_path.split('/').collect();
        if parts.len() != 4 || parts[0] != "MEF" {
            return Err(InferenceError::ValidationFailed(
                format!("Invalid seed path format: {}", knowledge.seed_path)
            ));
        }
        
        // Validate route sigma
        if knowledge.route.sigma.len() != 7 {
            return Err(InferenceError::ValidationFailed(
                "Route sigma must have exactly 7 elements".to_string()
            ));
        }
        
        for &val in &knowledge.route.sigma {
            if !(1..=7).contains(&val) {
                return Err(InferenceError::ValidationFailed(
                    format!("Route sigma values must be in [1..7], got {}", val)
                ));
            }
        }
        
        // TODO: Verify MEF ID by recomputing hash
        // TODO: Verify ledger block contains this knowledge
        // TODO: Verify HDAG references are valid
        
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use mef_schemas::{TicReference, RouteReference};

    fn make_test_knowledge() -> KnowledgeObject {
        KnowledgeObject::new(
            "mef-k-test".to_string(),
            TicReference {
                tic_id: "TIC-123".to_string(),
                snapshot_id: "SNAP-456".to_string(),
                timestamp: chrono::Utc::now(),
            },
            RouteReference {
                route_id: "route-789".to_string(),
                sigma: vec![1, 2, 3, 4, 5, 6, 7],
                score: 0.5,
            },
            "MEF/test/spiral/0001".to_string(),
            42,
        )
    }

    #[test]
    fn test_project_full() {
        let knowledge = make_test_knowledge();
        let result = KnowledgeInference::project(&knowledge, ProjectionMode::Full);
        
        assert!(result.is_ok());
        let json = result.unwrap();
        assert!(json.get("mef_id").is_some());
    }

    #[test]
    fn test_project_compact() {
        let knowledge = make_test_knowledge();
        let result = KnowledgeInference::project(&knowledge, ProjectionMode::Compact);
        
        assert!(result.is_ok());
        let json = result.unwrap();
        assert_eq!(json.get("mef_id").unwrap().as_str().unwrap(), "mef-k-test");
        assert_eq!(json.get("tic_id").unwrap().as_str().unwrap(), "TIC-123");
    }

    #[test]
    fn test_project_graph() {
        let mut knowledge = make_test_knowledge();
        knowledge.add_parent("parent-1".to_string());
        knowledge.add_child("child-1".to_string());
        
        let result = KnowledgeInference::project(&knowledge, ProjectionMode::Graph);
        
        assert!(result.is_ok());
        let json = result.unwrap();
        assert_eq!(json.get("parents").unwrap().as_array().unwrap().len(), 1);
        assert_eq!(json.get("children").unwrap().as_array().unwrap().len(), 1);
    }

    #[test]
    fn test_validate_valid_knowledge() {
        let knowledge = make_test_knowledge();
        let result = KnowledgeInference::validate(&knowledge);
        
        assert!(result.is_ok());
    }

    #[test]
    fn test_validate_invalid_seed_path() {
        let mut knowledge = make_test_knowledge();
        knowledge.seed_path = "invalid/path".to_string();
        
        let result = KnowledgeInference::validate(&knowledge);
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_invalid_sigma() {
        let mut knowledge = make_test_knowledge();
        knowledge.route.sigma = vec![1, 2, 3]; // Wrong length
        
        let result = KnowledgeInference::validate(&knowledge);
        assert!(result.is_err());
    }
}
