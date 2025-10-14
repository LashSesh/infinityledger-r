"""
Proof-of-Resonance (PoR) validation system.
Mathematical validation of Spiral snapshot stability.
"""

import json
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import hashlib

class ProofOfResonance:
    """
    Proof-of-Resonance validator for Spiral snapshots.
    FFT(s) → ŝ; r' = g(ŝ) ∈ [0,1]
    Acceptance: |r' - r_snapshot| ≤ δ ∧ λ_gap ≥ λ_min
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize PoR validator.
        
        Args:
            config: Configuration with validation parameters
        """
        self.config = config
        self.gate_config = config.get('gate', {})
        
        # Validation thresholds
        self.por_delta = self.gate_config.get('por_delta', 0.02)
        self.lambda_min = 0.1  # Minimum spectral gap
        self.stability_threshold = 0.9
        
        # Resonance parameters
        self.resonance_bands = {
            'low': (0.0, 0.3),
            'mid': (0.3, 0.7),
            'high': (0.7, 1.0)
        }
    
    def compute_fft_resonance(self, coordinates: List[float]) -> Tuple[float, np.ndarray]:
        """
        Compute resonance using FFT analysis.
        
        Args:
            coordinates: 5D spiral coordinates
            
        Returns:
            Tuple of (resonance value, FFT spectrum)
        """
        coords_array = np.array(coordinates)
        
        # Apply FFT
        fft_result = np.fft.fft(coords_array)
        fft_magnitude = np.abs(fft_result)
        
        # Normalize spectrum
        if np.max(fft_magnitude) > 0:
            fft_normalized = fft_magnitude / np.max(fft_magnitude)
        else:
            fft_normalized = fft_magnitude
        
        # Compute resonance metric
        # r' = mean(magnitude) / (1 + std(magnitude))
        mean_mag = np.mean(fft_normalized)
        std_mag = np.std(fft_normalized)
        
        resonance = float(mean_mag / (1 + std_mag))
        
        return resonance, fft_normalized
    
    def compute_spectral_gap(self, coordinates: List[float]) -> float:
        """
        Compute spectral gap using local Laplacian.
        
        Args:
            coordinates: 5D coordinates
            
        Returns:
            Spectral gap value
        """
        n = len(coordinates)
        
        if n < 3:
            # Too small for meaningful Laplacian
            return 0.5
        
        # Construct local Laplacian matrix
        # Using a circulant structure for 5D topology
        laplacian = np.zeros((n, n))

        for i in range(n):
            laplacian[i][i] = 2  # Diagonal
            laplacian[i][(i+1) % n] = -1  # Upper neighbor
            laplacian[i][(i-1) % n] = -1  # Lower neighbor
        
        # Compute eigenvalues
        eigenvalues = np.linalg.eigvalsh(laplacian)
        
        # Sort eigenvalues
        eigenvalues = np.sort(eigenvalues)
        
        # Spectral gap is difference between first two non-zero eigenvalues
        if len(eigenvalues) > 1:
            gap = float(eigenvalues[1] - eigenvalues[0])
        else:
            gap = 0.5
        
        return gap
    
    def compute_band_energy(self, spectrum: np.ndarray) -> Dict[str, float]:
        """
        Compute energy distribution across frequency bands.
        
        Args:
            spectrum: FFT magnitude spectrum
            
        Returns:
            Energy per band
        """
        n = len(spectrum)
        band_energy = {}
        
        for band_name, (low, high) in self.resonance_bands.items():
            # Calculate band indices
            low_idx = int(low * n)
            high_idx = int(high * n)
            
            # Compute energy in band
            band_spectrum = spectrum[low_idx:high_idx]
            energy = float(sum(float(v) ** 2 for v in band_spectrum))
            
            band_energy[band_name] = energy
        
        # Normalize
        total_energy = sum(band_energy.values())
        if total_energy > 0:
            band_energy = {k: v/total_energy for k, v in band_energy.items()}
        
        return band_energy
    
    def validate_resonance(self,
                          coordinates: List[float],
                          claimed_resonance: float) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate resonance claim for coordinates.
        
        Args:
            coordinates: 5D coordinates
            claimed_resonance: Claimed resonance value
            
        Returns:
            Tuple of (is_valid, validation_data)
        """
        # Compute FFT resonance
        fft_resonance, spectrum = self.compute_fft_resonance(coordinates)
        
        # Compute spectral gap
        spectral_gap = self.compute_spectral_gap(coordinates)
        
        # Compute band energies
        band_energy = self.compute_band_energy(spectrum)
        
        # Check resonance deviation
        resonance_deviation = abs(fft_resonance - claimed_resonance)
        resonance_valid = resonance_deviation <= self.por_delta
        
        # Check spectral gap
        gap_valid = spectral_gap >= self.lambda_min
        
        # Overall validation
        is_valid = resonance_valid and gap_valid
        
        validation_data = {
            "fft_resonance": fft_resonance,
            "claimed_resonance": claimed_resonance,
            "deviation": resonance_deviation,
            "spectral_gap": spectral_gap,
            "band_energy": band_energy,
            "resonance_valid": resonance_valid,
            "gap_valid": gap_valid,
            "status": "valid" if is_valid else "invalid"
        }
        
        return is_valid, validation_data
    
    def compute_stability_metric(self, 
                                coordinates: List[float],
                                history: Optional[List[List[float]]] = None) -> float:
        """
        Compute stability metric for coordinates.
        
        Args:
            coordinates: Current coordinates
            history: Optional history of previous coordinates
            
        Returns:
            Stability value in [0, 1]
        """
        coords_array = np.array(coordinates)
        
        # Base stability from norm
        base_stability = 1.0 / (1 + np.linalg.norm(coords_array - np.mean(coords_array)))
        
        if history and len(history) > 1:
            # Compute stability from history
            history_array = np.array(history)
            
            # Variance across history
            variance = np.var(history_array, axis=0)
            mean_variance = np.mean(variance)
            
            # Stability decreases with variance
            history_stability = 1.0 / (1 + mean_variance)
            
            # Combined stability
            stability = 0.7 * base_stability + 0.3 * history_stability
        else:
            stability = base_stability
        
        return float(min(1.0, max(0.0, stability)))
    
    def validate_snapshot(self, snapshot: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """
        Full validation of a Spiral snapshot.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            Tuple of (is_valid, validation_report)
        """
        coordinates = snapshot['coordinates']
        metrics = snapshot['metrics']
        
        # Validate resonance
        resonance_valid, resonance_data = self.validate_resonance(
            coordinates, 
            metrics['resonance']
        )
        
        # Compute stability
        stability = self.compute_stability_metric(coordinates)
        stability_valid = stability >= metrics.get('stability', 0) * 0.9
        
        # Check PoR status
        por_valid = metrics.get('por') == 'valid'
        
        # Overall validation
        is_valid = resonance_valid and stability_valid and por_valid
        
        report = {
            "snapshot_id": snapshot['id'],
            "resonance": resonance_data,
            "stability": {
                "computed": stability,
                "claimed": metrics.get('stability', 0),
                "valid": stability_valid
            },
            "por_status": metrics.get('por'),
            "overall_valid": is_valid,
            "timestamp": snapshot['timestamp']
        }
        
        return is_valid, report
    
    def batch_validate(self, snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate multiple snapshots in batch.
        
        Args:
            snapshots: List of snapshot data
            
        Returns:
            Batch validation results
        """
        results = {
            "total": len(snapshots),
            "valid": 0,
            "invalid": 0,
            "details": []
        }
        
        for snapshot in snapshots:
            is_valid, report = self.validate_snapshot(snapshot)
            
            if is_valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1
            
            results["details"].append(report)
        
        results["validation_rate"] = results["valid"] / results["total"] if results["total"] > 0 else 0
        
        return results
    
    def compute_network_resonance(self, snapshots: List[Dict[str, Any]]) -> float:
        """
        Compute aggregate resonance across multiple snapshots.
        
        Args:
            snapshots: List of snapshots
            
        Returns:
            Network-wide resonance metric
        """
        if not snapshots:
            return 0.0
        
        resonances = []
        for snapshot in snapshots:
            coords = snapshot['coordinates']
            resonance, _ = self.compute_fft_resonance(coords)
            resonances.append(resonance)
        
        # Network resonance is weighted mean
        # Weight by stability
        weights = [s['metrics'].get('stability', 0.5) for s in snapshots]
        
        if sum(weights) > 0:
            network_resonance = np.average(resonances, weights=weights)
        else:
            network_resonance = np.mean(resonances)
        
        return float(network_resonance)
    
    def generate_por_proof(self, snapshot: Dict[str, Any]) -> str:
        """
        Generate cryptographic proof string for PoR.
        
        Args:
            snapshot: Snapshot data
            
        Returns:
            Proof string (hash)
        """
        # Validate snapshot
        is_valid, report = self.validate_snapshot(snapshot)
        
        # Create proof data
        proof_data = {
            "snapshot_id": snapshot['id'],
            "coordinates": snapshot['coordinates'],
            "resonance": report['resonance']['fft_resonance'],
            "spectral_gap": report['resonance']['spectral_gap'],
            "stability": report['stability']['computed'],
            "valid": is_valid
        }
        
        # Generate deterministic proof string
        proof_str = json.dumps(proof_data, sort_keys=True)
        proof_hash = hashlib.sha256(proof_str.encode()).hexdigest()
        
        return proof_hash