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
pub mod quantum;
pub mod cube;
pub mod mandorla;
pub mod gabriel_cell;
pub mod qlogic;
pub mod resonance_tensor;
pub mod spiral_memory;
pub mod qdash_agent;
pub mod gates;

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
pub use quantum::{QuantumState, QuantumOperator};
pub use cube::{MetatronCube, NodeInfo, EdgeInfo, OperatorInfo};
pub use mandorla::MandorlaField;
pub use gabriel_cell::{GabrielCell, couple_cells, neighbor_feedback};
pub use qlogic::{QLOGICOscillatorCore, SpectralGrammar, EntropyAnalyzer, QLogicEngine, QLogicStepResult};
pub use resonance_tensor::ResonanceTensorField;
pub use spiral_memory::SpiralMemory;
pub use qdash_agent::{QDASHAgent, QDASHResult};
pub use gates::{MerkabaGate, TICCandidate, GateChecks, GateDecision, GateEvent, validate_gate_event};

#[cfg(test)]
mod tests {
    #[test]
    fn it_works() {
        let result = 2 + 2;
        assert_eq!(result, 4);
    }
}
