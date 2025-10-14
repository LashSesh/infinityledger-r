"""
merkaba_gate.py
---------------

Merkaba-Gate implementation as Mandorla layer between Solve-Coagula and TIC.
Integrates with Metatron Cube for topological routing and resonance calculations.

This gate serves as a deterministic filter ensuring only stable, coherent states
proceed to TIC crystallization and eventual ledger commitment.
"""

import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from pathlib import Path
import numpy as np
import hashlib

# Import Metatron Cube components
from src.mandorla import MandorlaField
from src.qlogic import QLogicEngine
from src.resonance_tensor import ResonanceTensorField
from src.gabriel_cell import GabrielCell
from src.spiralmemory import SpiralMemory
from src.cube import MetatronCube
from src.quantum import QuantumState, QuantumOperator
from src.qdash_agent import QDASHAgent


class MerkabaGate:
    """
    Merkaba-Gate implementation utilizing Metatron Cube's topological routing.
    
    The gate validates states through multiple checks:
    - Proof of Resonance (PoR)
    - Path Invariance (ΔPI)
    - Coherence measure (Φ)
    - Lyapunov stability (ΔV)
    - Optional Mirror Consistency Index (MCI) for dual-consensus
    """
    
    # Default threshold constants
    DEFAULT_EPSILON = 1e-6        # Path invariance threshold
    DEFAULT_PHI_STAR = 0.6        # Coherence threshold
    DEFAULT_ETA = 0.85            # MCI threshold (when applicable)
    DEFAULT_LYAPUNOV_WINDOW = 10  # Window for Lyapunov calculation
    
    def __init__(self, 
                 epsilon: float = DEFAULT_EPSILON,
                 phi_star: float = DEFAULT_PHI_STAR,
                 eta: float = DEFAULT_ETA,
                 metatron_nodes: int = 13,
                 audit_path: str = "logs/gate_merkaba.jsonl"):
        """
        Initialize Merkaba-Gate with Metatron Cube integration.
        
        Args:
            epsilon: Path invariance tolerance
            phi_star: Minimum coherence threshold
            eta: MCI threshold for dual-consensus
            metatron_nodes: Number of nodes in Metatron Cube (default 13)
            audit_path: Path for audit logging
        """
        self.epsilon = epsilon
        self.phi_star = phi_star
        self.eta = eta
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize Metatron Cube components
        self.metatron_cube = MetatronCube(full_edges=True)  # Full connectivity for maximum routing
        self.mandorla = MandorlaField(alpha=0.5, beta=0.5)
        self.qlogic = QLogicEngine(num_nodes=metatron_nodes)
        self.resonance_field = ResonanceTensorField(shape=(3, 3, 3))
        self.spiral_memory = SpiralMemory(alpha=0.07)
        self.qdash = QDASHAgent(n_cells=4, alpha=0.5, beta=0.5)
        
        # Track historical states for Lyapunov calculation
        self.state_history = []
        
    def compute_phi(self, tic_candidate: Dict[str, Any]) -> float:
        """
        Compute coherence measure Φ using Metatron Cube's resonance calculations.
        
        Args:
            tic_candidate: TIC candidate with fixpoint and invariants
            
        Returns:
            Coherence measure Φ ∈ [0, 1]
        """
        # Extract fixpoint coordinates
        fixpoint = np.array(tic_candidate.get("fixpoint", [0] * 5))
        
        # Pad to 13 dimensions for Metatron Cube
        if len(fixpoint) < 13:
            padded = np.zeros(13)
            padded[:len(fixpoint)] = fixpoint
            fixpoint = padded
        elif len(fixpoint) > 13:
            fixpoint = fixpoint[:13]
        
        # Create quantum state from fixpoint
        quantum_state = QuantumState(fixpoint, normalize=True)
        
        # Calculate resonance using Mandorla field
        self.mandorla.clear_inputs()
        
        # Add fixpoint vectors at different phases
        for phase in [0, np.pi/4, np.pi/2]:
            phase_shifted = fixpoint * np.exp(1j * phase)
            self.mandorla.add_input(np.real(phase_shifted[:5]))  # Use first 5 dims
        
        # Compute global resonance
        coherence = self.mandorla.calc_resonance()
        
        # Apply spectral analysis via QLOGIC
        qlogic_result = self.qlogic.step(t=tic_candidate.get("timestamp", 0))
        entropy = qlogic_result["entropy"]
        
        # Combine coherence with spectral entropy (lower entropy = higher coherence)
        phi = coherence * (1.0 - entropy / np.log2(13))  # Normalize entropy by max possible
        
        return float(np.clip(phi, 0, 1))
    
    def compute_delta_pi(self, tic_candidate: Dict[str, Any]) -> float:
        """
        Compute path invariance deviation ΔPI using Metatron's symmetry operators.
        
        Args:
            tic_candidate: TIC candidate with operator history
            
        Returns:
            Path invariance deviation ΔPI
        """
        # Get operator sequence from TIC candidate
        operator_sequence = tic_candidate.get("operator_sequence", [])
        if not operator_sequence:
            return 0.0  # No operators = perfect invariance
        
        # Generate alternative permutations using Metatron Cube
        c6_perms = self.metatron_cube.enumerate_group("C6")
        d6_perms = self.metatron_cube.enumerate_group("D6")
        
        fixpoint = np.array(tic_candidate.get("fixpoint", [0] * 5))
        
        # Pad fixpoint for Metatron operations
        if len(fixpoint) < 13:
            padded = np.zeros(13)
            padded[:len(fixpoint)] = fixpoint
            fixpoint = padded
        
        # Apply different permutation paths
        path_results = []
        
        # Original path
        original_result = fixpoint.copy()
        for op in operator_sequence:
            if op in ["DK", "SW", "PI", "WT"]:  # Apply stored operators
                original_result = self._apply_operator(original_result, op)
        path_results.append(original_result)
        
        # Apply symmetry permutations and check invariance
        for perm_info in c6_perms[:3]:  # Sample first 3 C6 permutations
            perm_matrix = np.array(perm_info["matrix"])
            permuted = perm_matrix @ fixpoint
            
            # Apply same operator sequence to permuted state
            result = permuted.copy()
            for op in operator_sequence:
                if op in ["DK", "SW", "PI", "WT"]:
                    result = self._apply_operator(result, op)
            
            # Unpermute result
            result = perm_matrix.T @ result
            path_results.append(result)
        
        # Calculate maximum deviation between paths
        delta_pi = 0.0
        for i in range(len(path_results)):
            for j in range(i + 1, len(path_results)):
                deviation = np.linalg.norm(path_results[i] - path_results[j])
                delta_pi = max(delta_pi, deviation)
        
        return float(delta_pi)
    
    def compute_delta_v(self, tic_candidate: Dict[str, Any]) -> float:
        """
        Compute Lyapunov exponent change ΔV to verify stability.
        
        Args:
            tic_candidate: TIC candidate
            
        Returns:
            Lyapunov change ΔV (negative = stable)
        """
        fixpoint = np.array(tic_candidate.get("fixpoint", [0] * 5))
        
        # Add to history
        self.state_history.append(fixpoint)
        if len(self.state_history) > self.DEFAULT_LYAPUNOV_WINDOW:
            self.state_history.pop(0)
        
        if len(self.state_history) < 2:
            return 0.0  # Not enough history
        
        # Calculate Lyapunov exponent using resonance field dynamics
        lyapunov_sum = 0.0
        for i in range(1, len(self.state_history)):
            prev_state = self.state_history[i-1]
            curr_state = self.state_history[i]
            
            # Measure divergence
            delta = curr_state - prev_state
            if np.linalg.norm(prev_state) > 0:
                divergence = np.log(np.linalg.norm(delta) / np.linalg.norm(prev_state) + 1e-10)
                lyapunov_sum += divergence
        
        # Average Lyapunov over window
        lyapunov_avg = lyapunov_sum / (len(self.state_history) - 1)
        
        # Calculate change (current - previous average)
        if len(self.state_history) >= 3:
            # Previous Lyapunov (excluding current state)
            prev_sum = 0.0
            for i in range(1, len(self.state_history) - 1):
                prev_state = self.state_history[i-1]
                curr_state = self.state_history[i]
                delta = curr_state - prev_state
                if np.linalg.norm(prev_state) > 0:
                    divergence = np.log(np.linalg.norm(delta) / np.linalg.norm(prev_state) + 1e-10)
                    prev_sum += divergence
            prev_avg = prev_sum / (len(self.state_history) - 2)
            
            delta_v = lyapunov_avg - prev_avg
        else:
            delta_v = lyapunov_avg
        
        return float(delta_v)
    
    def compute_mci(self, tic_candidate: Dict[str, Any]) -> Optional[float]:
        """
        Compute Mirror Consistency Index using QDASH dual paths.
        
        Args:
            tic_candidate: TIC candidate
            
        Returns:
            MCI value if dual consensus available, None otherwise
        """
        # Check if dual path information is available
        if "dual_fixpoint" not in tic_candidate:
            return None
        
        primal_fixpoint = np.array(tic_candidate.get("fixpoint", [0] * 5))
        dual_fixpoint = np.array(tic_candidate.get("dual_fixpoint", [0] * 5))
        
        # Normalize for comparison
        if np.linalg.norm(primal_fixpoint) > 0:
            primal_normalized = primal_fixpoint / np.linalg.norm(primal_fixpoint)
        else:
            primal_normalized = primal_fixpoint
        
        if np.linalg.norm(dual_fixpoint) > 0:
            dual_normalized = dual_fixpoint / np.linalg.norm(dual_fixpoint)
        else:
            dual_normalized = dual_fixpoint
        
        # Calculate consistency as cosine similarity
        mci = np.dot(primal_normalized, dual_normalized)
        
        # Map to [0, 1] range
        mci = (mci + 1.0) / 2.0
        
        return float(mci)
    
    def merkaba_decide(self,
                      por: str,
                      delta_pi: float,
                      phi: float,
                      delta_v: float,
                      mci: Optional[float],
                      eps: float,
                      phi_star: float,
                      eta: Optional[float]) -> Tuple[bool, str]:
        """
        Make gate decision based on all criteria.
        
        Args:
            por: Proof of Resonance status
            delta_pi: Path invariance deviation
            phi: Coherence measure
            delta_v: Lyapunov change
            mci: Mirror Consistency Index (optional)
            eps: Path invariance threshold
            phi_star: Coherence threshold
            eta: MCI threshold (if MCI provided)
            
        Returns:
            Tuple of (commit decision, reason string)
        """
        reasons = []
        
        # Check PoR
        if por != "valid":
            reasons.append(f"por={por}")
            return False, f"rejected: {', '.join(reasons)}"
        
        # Check path invariance
        if delta_pi > eps:
            reasons.append(f"path_invariance_exceeded: {delta_pi:.6f} > {eps}")
            return False, f"rejected: {', '.join(reasons)}"
        
        # Check coherence
        if phi < phi_star:
            reasons.append(f"coherence_insufficient: {phi:.3f} < {phi_star}")
            return False, f"rejected: {', '.join(reasons)}"
        
        # Check Lyapunov stability
        if delta_v >= 0:
            reasons.append(f"lyapunov_unstable: {delta_v:.6f} >= 0")
            return False, f"rejected: {', '.join(reasons)}"
        
        # Check MCI if available
        if mci is not None and eta is not None:
            if mci < eta:
                reasons.append(f"mci_insufficient: {mci:.3f} < {eta}")
                return False, f"rejected: {', '.join(reasons)}"
        
        return True, "all_thresholds_passed"
    
    def run_merkaba(self,
                   snapshot_id: str,
                   tic_candidate_id: str,
                   params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute complete Merkaba-Gate evaluation.
        
        Args:
            snapshot_id: Snapshot identifier
            tic_candidate_id: TIC candidate identifier
            params: Optional parameter overrides
            
        Returns:
            Gate event artifact
        """
        # Load TIC candidate (in production, this would fetch from storage)
        tic_candidate = self._load_tic_candidate(tic_candidate_id)
        
        # Use provided params or defaults
        if params is None:
            params = {}
        
        eps = params.get("epsilon", self.epsilon)
        phi_star = params.get("phi_star", self.phi_star)
        eta = params.get("eta", self.eta)
        
        # Compute all gate checks
        por = tic_candidate.get("proof", {}).get("por", "invalid")
        delta_pi = self.compute_delta_pi(tic_candidate)
        phi = self.compute_phi(tic_candidate)
        delta_v = self.compute_delta_v(tic_candidate)
        mci = self.compute_mci(tic_candidate)
        
        # Make decision
        commit, reason = self.merkaba_decide(
            por, delta_pi, phi, delta_v, mci,
            eps, phi_star, eta if mci is not None else None
        )
        
        # Create gate event
        gate_event = {
            "gate_id": str(uuid.uuid4()),
            "snapshot_id": snapshot_id,
            "tic_candidate_id": tic_candidate_id,
            "checks": {
                "por": por,
                "delta_pi": float(delta_pi),
                "phi": float(phi),
                "delta_v": float(delta_v)
            },
            "decision": {
                "commit": commit,
                "reason": reason
            },
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Add MCI if computed
        if mci is not None:
            gate_event["checks"]["mci"] = float(mci)
        
        # Audit log
        self._audit_event(gate_event)
        
        return gate_event
    
    def _apply_operator(self, state: np.ndarray, operator: str) -> np.ndarray:
        """
        Apply MEF operator to state vector.
        
        Args:
            state: Current state vector
            operator: Operator name (DK, SW, PI, WT)
            
        Returns:
            Transformed state
        """
        if operator == "DK":  # DoubleKick
            # Apply orthogonal impulses
            u1 = np.random.randn(len(state))
            u1 = u1 / np.linalg.norm(u1)
            u2 = np.random.randn(len(state))
            u2 = u2 - np.dot(u2, u1) * u1
            u2 = u2 / np.linalg.norm(u2) if np.linalg.norm(u2) > 0 else u2
            
            alpha1, alpha2 = 0.05, -0.03
            return state + alpha1 * u1 + alpha2 * u2
        
        elif operator == "SW":  # Sweep
            # Apply threshold sweep
            mean_val = np.mean(state)
            tau = 0.5
            beta = 0.1
            gate = 1.0 / (1.0 + np.exp(-(mean_val - tau) / beta))
            return gate * state
        
        elif operator == "PI":  # Path Invariance
            # Sort to canonical form
            return np.sort(state)
        
        elif operator == "WT":  # Weight Transfer
            # Transfer weights between scales
            gamma = 0.1
            micro = state[:len(state)//3]
            meso = state[len(state)//3:2*len(state)//3]
            macro = state[2*len(state)//3:]
            
            # Redistribute weights
            total_weight = np.sum(np.abs(state))
            if total_weight > 0:
                new_state = state.copy()
                new_state[:len(state)//3] *= (1 - gamma)
                new_state[len(state)//3:] *= (1 + gamma * 0.5)
                return new_state
            return state
        
        return state
    
    def _load_tic_candidate(self, tic_id: str) -> Dict[str, Any]:
        """
        Load TIC candidate from storage.
        
        Args:
            tic_id: TIC identifier
            
        Returns:
            TIC candidate dictionary
        """
        # Mock implementation - in production, load from actual storage
        return {
            "tic_id": tic_id,
            "fixpoint": [0.5, 0.3, 0.7, 0.2, 0.9],
            "proof": {"por": "valid"},
            "operator_sequence": ["DK", "SW", "PI", "WT"],
            "timestamp": 0
        }
    
    def _audit_event(self, event: Dict[str, Any]):
        """
        Write gate event to audit log.
        
        Args:
            event: Gate event to audit
        """
        with open(self.audit_path, 'a') as f:
            f.write(json.dumps(event) + '\n')


def validate_gate_event(event: Dict[str, Any]) -> bool:
    """
    Validate gate event against schema.
    
    Args:
        event: Gate event to validate
        
    Returns:
        True if valid, False otherwise
    """
    required_fields = ["gate_id", "snapshot_id", "tic_candidate_id", "checks", "decision", "timestamp"]
    required_checks = ["por", "delta_pi", "phi", "delta_v"]
    required_decision = ["commit", "reason"]
    
    # Check top-level fields
    for field in required_fields:
        if field not in event:
            return False
    
    # Check checks sub-fields
    for field in required_checks:
        if field not in event["checks"]:
            return False
    
    # Check decision sub-fields
    for field in required_decision:
        if field not in event["decision"]:
            return False
    
    # Validate data types
    if not isinstance(event["decision"]["commit"], bool):
        return False
    
    if event["checks"]["por"] not in ["valid", "invalid"]:
        return False
    
    return True