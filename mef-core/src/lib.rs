/*!
 * MEF-Core Utilities
 * 
 * Core utility modules providing foundational functionality across the MEF workspace.
 */

pub mod geometry;
pub mod field_vector;
pub mod mef_pipeline;
pub mod graph;
pub mod symmetries;

pub use geometry::{
    Node, canonical_nodes, canonical_edges, complete_canonical_edges,
    get_metatron_nodes, get_metatron_edges, find_node,
};
pub use field_vector::FieldVector;
pub use mef_pipeline::{MEFCore, MEFCoreConfig, ProcessingResult};
pub use graph::MetatronCubeGraph;
pub use symmetries::{
    generate_s7_permutations, permutation_matrix, permutation_to_matrix,
    apply_permutation_to_adjacency, hexagon_rotation, hexagon_reflection,
    generate_c6_subgroup, generate_d6_subgroup, generate_symmetric_group,
    generate_alternating_group,
};

#[cfg(test)]
mod tests {
    #[test]
    fn it_works() {
        let result = 2 + 2;
        assert_eq!(result, 4);
    }
}
