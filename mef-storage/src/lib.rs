/*!
 * MEF-Core Storage Module
 * 
 * Provides cloud storage capabilities for MEF-Core artifacts including
 * snapshots, TICs, and ledger blocks.
 */

pub mod s3_adapter;

pub use s3_adapter::{
    S3StorageAdapter,
    S3Config,
    ArtifactType,
    UploadMetadata,
    ArtifactMetadata,
    SyncStats,
    StorageMetrics,
    ArtifactStats,
};
