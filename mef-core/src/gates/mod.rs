/*!
 * Gates Module
 * 
 * Collection of gate implementations for MEF-Core processing pipeline.
 */

pub mod merkaba_gate;

pub use merkaba_gate::{
    MerkabaGate, TICCandidate, GateChecks, GateDecision, GateEvent,
    validate_gate_event,
};
