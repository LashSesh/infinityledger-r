/*!
 * MEF-Core Specs Module
 * 
 * Provides blueprint loading and validation for SPEC-002 compliant configurations.
 */

pub mod blueprint_models;
pub mod blueprint_loader;

pub use blueprint_models::{Spec, Component, API, Storage, Blueprint};
pub use blueprint_loader::{
    BlueprintDocument, BlueprintValidationError, BlueprintSchemaError,
    load_blueprint, REQUIRED_TOP_LEVEL_KEYS,
};
