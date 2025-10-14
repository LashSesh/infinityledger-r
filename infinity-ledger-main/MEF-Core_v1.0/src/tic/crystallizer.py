"""
Temporal Information Crystal (TIC) implementation.
Crystalline attractors from Solve-Coagula fixpoints with multiscale gating.
"""

import json
import uuid
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
try:
    import jsonschema
except ImportError:  # pragma: no cover - optional dependency
    jsonschema = None

class TICCrystallizer:
    """
    TIC crystallization system with multiscale gating.
    Converts Solve-Coagula fixpoints into stable crystals.
    """
    
    def __init__(self, config: Dict[str, Any], store_path: str = "C:/MEF/store"):
        """
        Initialize TIC Crystallizer.
        
        Args:
            config: Configuration parameters
            store_path: Storage directory path
        """
        self.config = config
        self.gate_config = config.get('gate', {})
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # Gating thresholds
        self.por_delta = self.gate_config.get('por_delta', 0.02)
        self.phi_star = self.gate_config.get('phi_star', 0.6)
        self.mci_min = self.gate_config.get('mci_min', 0.9)
        
        # Multiscale thresholds
        self.theta_micro = 0.7
        self.theta_meso = 0.6
        self.theta_macro = 0.5
        
        # Load JSON schema for validation
        schema_path = Path(__file__).parent.parent / "schemas" / "tic.json"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            self.schema = None
    
    def compute_invariants(self, fixpoint: np.ndarray, trajectory: List[np.ndarray]) -> Dict[str, float]:
        """
        Compute invariant metrics from fixpoint and convergence trajectory.
        
        Args:
            fixpoint: Converged fixpoint vector
            trajectory: List of vectors from convergence
            
        Returns:
            Dictionary of invariant values
        """
        if len(trajectory) < 2:
            trajectory = [fixpoint, fixpoint]
        
        trajectory_list = [list(map(float, vec)) for vec in trajectory]
        flat_values = [value for vec in trajectory_list for value in vec]
        variance = float(np.var(flat_values)) if flat_values else 0.0

        # Retention: how much of initial structure is preserved
        if trajectory_list:
            initial_vec = np.array(trajectory_list[0])
            fixpoint_vec = np.array(fixpoint)
            denom = np.linalg.norm(fixpoint_vec) * np.linalg.norm(initial_vec)
            retention = float(np.dot(fixpoint_vec, initial_vec) / denom) if denom else 1.0
        else:
            retention = 1.0

        # Spectral gap (simplified)
        if len(trajectory_list) > 3:
            cov = np.cov(trajectory_list)
            eigenvalues = np.linalg.eigvalsh(cov)
            gap = float(eigenvalues[-1] - eigenvalues[-2]) if len(eigenvalues) > 1 else 0.5
        else:
            gap = 0.5
        
        return {
            "variance": variance,
            "retention": abs(retention),
            "gap": gap
        }
    
    def compute_sigma_bar(self, fixpoint: np.ndarray, seed: str) -> Dict[str, float]:
        """
        Compute aggregated sigma values for TIC.
        
        Args:
            fixpoint: Fixpoint vector
            seed: Deterministic seed
            
        Returns:
            Sigma bar values
        """
        # Generate deterministic values from seed and fixpoint
        seed_hash = hashlib.sha256((seed + str(fixpoint.tolist())).encode()).digest()
        seed_vals = [int.from_bytes(seed_hash[i:i+4], 'big') / (2**32) 
                     for i in range(0, 12, 4)]
        
        psi = float(np.tanh(np.linalg.norm(fixpoint) * seed_vals[0]))
        rho = float(np.abs(np.sin(np.sum(fixpoint) * seed_vals[1])))
        omega = float(np.cos(np.mean(fixpoint) * seed_vals[2]))
        
        return {
            "psi": psi,
            "rho": rho, 
            "omega": omega
        }
    
    def compute_pi_gap(self, fixpoint: np.ndarray, original: np.ndarray) -> float:
        """
        Compute path invariance deviation.
        
        Args:
            fixpoint: Converged fixpoint
            original: Original vector
            
        Returns:
            Path invariance gap value
        """
        # Compute deviation from path invariance
        # Using cyclic permutations as proxy
        deviations = []
        
        n = len(fixpoint) or 1
        for shift in range(n):
            shifted = np.roll(fixpoint, shift)
            dev = np.linalg.norm(shifted - fixpoint)
            base = np.linalg.norm(fixpoint) or 1.0
            dev = (dev / base) / n
            deviations.append(dev)

        raw = float(np.mean(deviations))
        return raw * 1e-3
    
    def compute_mci(self, fixpoint: np.ndarray) -> float:
        """
        Compute Mirror Consistency Index.
        
        Args:
            fixpoint: Fixpoint vector
            
        Returns:
            MCI value in [0, 1]
        """
        # Mirror consistency: symmetry measure
        reversed_fp = fixpoint[::-1]
        consistency = 1.0 - np.linalg.norm(fixpoint - reversed_fp) / (2 * np.linalg.norm(fixpoint))
        return float(max(0, min(1, consistency)))
    
    def validate_proof(self, 
                      por_status: str, 
                      pi_gap: float, 
                      mci: float,
                      phi: float) -> Tuple[str, Dict[str, Any]]:
        """
        Validate proof for TIC acceptance.
        
        Args:
            por_status: Proof-of-Resonance status
            pi_gap: Path invariance gap
            mci: Mirror Consistency Index
            phi: Order parameter
            
        Returns:
            Tuple of (validation status, proof dict)
        """
        # Merkaba gate conditions
        por_valid = (por_status == "valid")
        pi_valid = (pi_gap <= self.por_delta)
        phi_valid = (phi >= self.phi_star)
        mci_valid = (mci >= self.mci_min)
        
        all_valid = por_valid and pi_valid and phi_valid and mci_valid
        
        proof = {
            "por": por_status,
            "pi_gap": pi_gap,
            "mci": mci
        }
        
        return ("valid" if all_valid else "invalid"), proof
    
    def multiscale_gating(self, units: List[float]) -> Dict[str, Any]:
        """
        Implement multiscale gating mechanism.
        β_micro = 1{Z_U ≥ θ_μ}
        β_meso = 1{Σ_U w_U β_micro ≥ θ_m}
        β_macro = 1{Σ_C W_C β_meso ≥ θ_M}
        
        Args:
            units: List of unit activation values
            
        Returns:
            Gating results
        """
        # Micro level gating
        beta_micro = [1 if z >= self.theta_micro else 0 for z in units]
        micro_rate = sum(beta_micro) / len(beta_micro) if beta_micro else 0
        
        # Meso level gating (weighted average)
        weights_meso = np.ones(len(beta_micro)) / len(beta_micro)  # Uniform weights
        beta_meso = 1 if np.dot(weights_meso, beta_micro) >= self.theta_meso else 0
        
        # Macro level gating
        beta_macro = 1 if beta_meso >= self.theta_macro else 0
        
        return {
            "micro": {
                "activations": beta_micro,
                "rate": micro_rate,
                "passed": micro_rate >= self.theta_micro
            },
            "meso": {
                "value": beta_meso,
                "passed": bool(beta_meso)
            },
            "macro": {
                "value": beta_macro,
                "passed": bool(beta_macro),
                "commit": bool(beta_macro)  # Commit only if macro gate passes
            }
        }
    
    def create_tic(self,
                  fixpoint: np.ndarray,
                  snapshot_id: str,
                  seed: str,
                  convergence_info: Dict[str, Any],
                  snapshot_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a TIC from Solve-Coagula fixpoint.
        
        Args:
            fixpoint: Converged fixpoint vector
            snapshot_id: Source snapshot ID
            seed: Deterministic seed
            convergence_info: Convergence information from Solve-Coagula
            snapshot_data: Original snapshot data
            
        Returns:
            TIC dictionary
        """
        hash_input = f"{snapshot_id}_{seed}_{fixpoint.tolist()}"
        tic_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        tic_id = tic_hash[:16]

        base_time = datetime(2025, 1, 1)
        seconds_offset = int(tic_hash[16:24], 16) % 86400
        current_time = base_time + timedelta(seconds=seconds_offset)
        
        # Time window (last 5 minutes for this TIC)
        window = [
            (current_time - timedelta(minutes=5)).isoformat(),
            current_time.isoformat()
        ]
        
        # Extract convergence trajectory if available
        trajectory = []
        if convergence_info.get('history'):
            trajectory = [np.array([h['norm']] * 5) for h in convergence_info['history'][:10]]
        
        # Compute TIC components
        invariants = self.compute_invariants(fixpoint, trajectory)
        sigma_bar = self.compute_sigma_bar(fixpoint, seed)

        # Compute proof components
        pi_gap = self.compute_pi_gap(fixpoint, np.array(snapshot_data['coordinates']))
        mci = self.compute_mci(fixpoint)
        phi = snapshot_data['metrics']['resonance']  # Use resonance as order parameter

        # Validate proof
        por_status = snapshot_data['metrics']['por']
        validation_status, proof = self.validate_proof(por_status, pi_gap, mci, phi)

        invariants['delta_pi'] = pi_gap

        # Create TIC structure
        tic = {
            "tic_id": tic_id,
            "seed": seed,
            "fixpoint": fixpoint.tolist(),
            "window": window,
            "invariants": invariants,
            "sigma_bar": sigma_bar,
            "proof": proof,
            "source_snapshot": snapshot_id
        }
        
        # Validate against schema if available
        if self.schema and jsonschema:
            try:
                jsonschema.validate(instance=tic, schema=self.schema)
            except jsonschema.exceptions.ValidationError as e:
                print(f"TIC schema validation warning: {e}")
        
        return tic
    
    def save_tic(self, tic: Dict[str, Any]) -> str:
        """
        Save TIC to disk.
        
        Args:
            tic: TIC data
            
        Returns:
            Path to saved TIC file
        """
        tic_file = self.store_path / f"{tic['tic_id']}.tic"
        
        with open(tic_file, 'w') as f:
            json.dump(tic, f, indent=2)
        
        return str(tic_file)
    
    def load_tic(self, tic_id: str) -> Optional[Dict[str, Any]]:
        """
        Load TIC from disk.
        
        Args:
            tic_id: TIC UUID
            
        Returns:
            TIC data or None if not found
        """
        tic_file = self.store_path / f"{tic_id}.tic"
        
        if not tic_file.exists():
            return None
        
        with open(tic_file, 'r') as f:
            return json.load(f)
    
    def should_commit(self, tic: Dict[str, Any]) -> bool:
        """
        Determine if TIC should be committed to ledger.
        
        Args:
            tic: TIC data
            
        Returns:
            True if TIC passes all gating criteria
        """
        # Check proof validity
        if tic['proof']['por'] != 'valid':
            return False
        
        # Check invariants
        if tic['invariants']['gap'] < 0.1:
            return False
        
        # Check MCI threshold
        if tic['proof']['mci'] < self.mci_min:
            return False
        
        # Multiscale gating on fixpoint components
        gating = self.multiscale_gating(tic['fixpoint'])
        
        return gating['macro']['commit']
    
    def get_tic_hash(self, tic: Dict[str, Any]) -> str:
        """
        Compute deterministic hash of TIC.
        
        Args:
            tic: TIC data
            
        Returns:
            SHA256 hash string
        """
        tic_str = json.dumps(tic, sort_keys=True)
        return hashlib.sha256(tic_str.encode()).hexdigest()