"""
Spiral Snapshot implementation for 5D storage.
Deterministic transformation and addressing system.
"""

import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
try:
    import jsonschema
except ImportError:  # pragma: no cover - optional dependency
    jsonschema = None

class SpiralSnapshot:
    """
    5D Spiral storage implementation with deterministic addressing.
    """
    
    def __init__(self, config: Dict[str, Any], store_path: str = "C:/MEF/store"):
        """
        Initialize Spiral Snapshot system.
        
        Args:
            config: Spiral configuration parameters
            store_path: Path to storage directory
        """
        self.config = config
        self.store_path = Path(store_path)
        self.store_path.mkdir(parents=True, exist_ok=True)

        self._sequence = 0
        
        # Spiral parameters from config
        self.r = config.get('r', 1.0)
        self.a = config.get('a', 0.05)
        self.b = config.get('b', 0.2)
        self.c = config.get('c', 0.2)
        self.k = config.get('k', 2)
        self.step = config.get('step', 0.01)
        
        # Load JSON schema for validation
        schema_path = Path(__file__).parent.parent / "schemas" / "spiral_snapshot.json"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
        else:
            self.schema = None
    
    def compute_coordinates(self, theta: float, seed: str) -> List[float]:
        """
        Compute 5D spiral coordinates for given phase.
        s(θ) = (r cos θ, r sin θ, aθ, b sin(kθ), c cos(kθ))
        
        Args:
            theta: Phase parameter
            seed: Deterministic seed for modifications
            
        Returns:
            List of 5 coordinates
        """
        # Generate deterministic modification from seed
        seed_hash = hashlib.sha256(seed.encode()).digest()
        seed_mod = int.from_bytes(seed_hash[:4], 'big') / (2**32)
        
        # Apply seed-based deterministic modification
        r_mod = self.r * (1 + 0.1 * seed_mod)
        
        coords = [
            r_mod * np.cos(theta),           # x1
            r_mod * np.sin(theta),           # x2
            self.a * theta,                  # x3
            self.b * np.sin(self.k * theta), # x4
            self.c * np.cos(self.k * theta)  # x5
        ]
        
        return coords
    
    def compute_sigma(self, coords: List[float], seed: str) -> Dict[str, float]:
        """
        Compute sigma values for resonance metrics.
        
        Args:
            coords: 5D coordinates
            seed: Deterministic seed
            
        Returns:
            Dictionary with psi, rho, omega values
        """
        # Deterministic sigma computation
        seed_hash = hashlib.sha256(seed.encode()).digest()
        seed_vals = [int.from_bytes(seed_hash[i:i+4], 'big') / (2**32) 
                     for i in range(0, 12, 4)]
        
        coords_array = np.array(coords)
        
        # Compute deterministic sigma values
        psi = float(np.tanh(np.dot(coords_array, coords_array) * seed_vals[0]))
        rho = float(np.abs(np.sin(np.sum(coords_array) * seed_vals[1])))
        omega = float(np.cos(np.prod(np.abs(coords_array[:3])) * seed_vals[2]))
        
        return {
            "psi": psi,
            "rho": rho,
            "omega": omega
        }
    
    def compute_resonance(self, coords: List[float], sigma: Dict[str, float]) -> float:
        """
        Compute resonance metric for stability validation.
        
        Args:
            coords: 5D coordinates
            sigma: Sigma values
            
        Returns:
            Resonance value in [0, 1]
        """
        coords_array = np.array(coords)
        
        # Resonance function: F(q, θ) = σ(⟨u(q), u(θ)⟩ + α·κ(q,θ) - β·d_T(q,θ))
        inner_product = np.dot(coords_array, coords_array)
        kernel_value = np.exp(-np.linalg.norm(coords_array)**2 / 2)
        topology_distance = np.sqrt(np.sum(coords_array**2))
        
        resonance = float(np.tanh(
            inner_product * sigma["psi"] + 
            0.5 * kernel_value - 
            0.3 * topology_distance / (1 + topology_distance)
        ))
        
        return abs(resonance)
    
    def compute_stability(self, coords: List[float], resonance: float) -> float:
        """
        Compute stability metric for snapshot.
        
        Args:
            coords: 5D coordinates
            resonance: Resonance value
            
        Returns:
            Stability value in [0, 1]
        """
        coords_array = np.array(coords)
        
        # Stability based on spectral properties
        if len(coords) >= 3:
            # Create a small Laplacian for local neighborhood
            local_laplacian = np.array([
                [2, -1, 0],
                [-1, 2, -1],
                [0, -1, 2]
            ])
            
            # Compute eigenvalues
            eigenvalues = np.linalg.eigvalsh(local_laplacian)
            spectral_gap = eigenvalues[1] - eigenvalues[0] if len(eigenvalues) > 1 else 0
            
            stability = float(np.tanh(spectral_gap * resonance))
        else:
            stability = resonance * 0.8
        
        return abs(stability)
    
    def validate_por(self, coords: List[float], resonance: float, delta: float = 0.02) -> str:
        """
        Proof-of-Resonance validation.
        
        Args:
            coords: 5D coordinates
            resonance: Computed resonance
            delta: Acceptance threshold
            
        Returns:
            "valid" or "invalid"
        """
        coords_array = np.array(coords)
        
        # FFT-based validation
        fft_result = np.fft.fft(coords_array)
        fft_magnitude = np.abs(fft_result)
        
        # Compute resonance from FFT
        fft_resonance = float(np.mean(fft_magnitude) / (1 + np.std(fft_magnitude)))
        
        # Check spectral gap
        if len(coords) >= 3:
            local_laplacian = np.array([[2, -1, 0], [-1, 2, -1], [0, -1, 2]])
            eigenvalues = np.linalg.eigvalsh(local_laplacian)
            spectral_gap = eigenvalues[1] - eigenvalues[0] if len(eigenvalues) > 1 else 0
        else:
            spectral_gap = 0.5
        
        # Validation criteria
        resonance_check = abs(fft_resonance - resonance) <= delta
        gap_check = spectral_gap >= 0.1  # minimum spectral gap
        
        return "valid" if (resonance_check and gap_check) else "invalid"
    
    def create_snapshot(self, 
                       data: Any, 
                       seed: str,
                       phase: Optional[float] = None) -> Dict[str, Any]:
        """
        Create a new Spiral Snapshot from raw data.
        
        Args:
            data: Raw input data
            seed: Deterministic seed
            phase: Optional phase parameter (auto-computed if None)
            
        Returns:
            Snapshot dictionary
        """
        # Generate snapshot ID
        base_payload = json.dumps(data, sort_keys=True) if isinstance(data, dict) else str(data)
        id_source = f"{base_payload}_{seed}"
        snapshot_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

        base_time = datetime(2025, 1, 1)
        time_hash = hashlib.sha256((snapshot_id + seed).encode()).digest()
        sequence_offset = timedelta(minutes=5 * self._sequence)
        hash_offset = timedelta(seconds=int.from_bytes(time_hash[:4], 'big') % 300)
        timestamp = (base_time + sequence_offset + hash_offset).isoformat()
        self._sequence += 1
        
        # Compute phase if not provided
        if phase is None:
            # Deterministic phase from data and seed
            data_str = json.dumps(data) if not isinstance(data, str) else data
            phase_hash = hashlib.sha256((data_str + seed).encode()).digest()
            phase = float(int.from_bytes(phase_hash[:4], 'big') / (2**32)) * 2 * np.pi
        
        # Compute spiral coordinates
        coordinates = self.compute_coordinates(phase, seed)
        
        # Compute sigma values
        sigma = self.compute_sigma(coordinates, seed)
        
        # Compute metrics
        resonance = self.compute_resonance(coordinates, sigma)
        stability = self.compute_stability(coordinates, resonance)
        por_status = self.validate_por(coordinates, resonance, self.config.get('por_delta', 0.02))
        
        # Create snapshot structure
        snapshot = {
            "id": snapshot_id,
            "timestamp": timestamp,
            "seed": seed,
            "phase": phase,
            "coordinates": coordinates,
            "sigma": sigma,
            "metrics": {
                "resonance": resonance,
                "stability": stability,
                "por": por_status
            },
            "payload": {
                "data": data if isinstance(data, dict) else {"raw": str(data)},
                "type": type(data).__name__
            },
            "hdag_node": f"N-{snapshot_id}"
        }
        
        # Validate against schema if available
        if self.schema and jsonschema:
            try:
                jsonschema.validate(instance=snapshot, schema=self.schema)
            except jsonschema.exceptions.ValidationError as e:
                print(f"Schema validation warning: {e}")
        
        return snapshot
    
    def save_snapshot(self, snapshot: Dict[str, Any]) -> str:
        """
        Save snapshot to disk.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            Path to saved snapshot file
        """
        snapshot_file = self.store_path / f"{snapshot['id']}.spiral"
        
        with open(snapshot_file, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        return str(snapshot_file)
    
    def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Load snapshot from disk.
        
        Args:
            snapshot_id: UUID of snapshot
            
        Returns:
            Snapshot data or None if not found
        """
        snapshot_file = self.store_path / f"{snapshot_id}.spiral"
        
        if not snapshot_file.exists():
            return None
        
        with open(snapshot_file, 'r') as f:
            return json.load(f)
    
    def find_optimal_phase(self, query: Any, seed: str) -> float:
        """
        Find optimal phase for query using resonance maximization.
        θ* = arg max F(q, θ)
        
        Args:
            query: Query data
            seed: Deterministic seed
            
        Returns:
            Optimal phase value
        """
        best_phase = 0.0
        best_resonance = -float('inf')
        
        # Search over phase space
        for i in range(100):
            test_phase = i * 2 * np.pi / 100
            coords = self.compute_coordinates(test_phase, seed)
            sigma = self.compute_sigma(coords, seed)
            resonance = self.compute_resonance(coords, sigma)
            
            if resonance > best_resonance:
                best_resonance = resonance
                best_phase = test_phase
        
        return best_phase
    
    def get_snapshot_hash(self, snapshot: Dict[str, Any]) -> str:
        """
        Compute deterministic hash of snapshot.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            SHA256 hash string
        """
        # Create deterministic string representation
        snapshot_str = json.dumps(snapshot, sort_keys=True)
        return hashlib.sha256(snapshot_str.encode()).hexdigest()