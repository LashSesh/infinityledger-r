"""
DoubleKick (DK) operator implementation - SPEC-002 konform.
Local unsticking through dual impulse without expansion.
"""

import numpy as np
from typing import Dict, Any

# Import SPEC-002 Funktion
from .operators import dk as dk_function

class DoubleKick:
    """
    DoubleKick operator: DK(v) = v + α₁u₁ + α₂u₂
    where ⟨u₁, u₂⟩ = 0 and ||u_i||₂ ≤ 1
    Maintains non-expansiveness: |α₁| + |α₂| ≤ η with η ≪ 1
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize DoubleKick operator.
        
        Args:
            config: Configuration with alpha1, alpha2 parameters
        """
        self.alpha1 = config.get('alpha1', 0.05)
        self.alpha2 = config.get('alpha2', -0.03)
        
        # Verify constraint |α₁| + |α₂| ≤ η
        self.eta = abs(self.alpha1) + abs(self.alpha2)
        if self.eta > 0.1:
            print(f"Warning: DoubleKick η={self.eta} > 0.1, may affect contractivity")
        
        # Generate orthogonal unit vectors deterministically
        self._generate_orthogonal_vectors()
    
    def _generate_orthogonal_vectors(self):
        """Generate two orthogonal unit vectors u₁ and u₂."""
        np.random.seed(42)  # Deterministic generation
        
        # Generate first unit vector
        u1 = np.random.randn(5)
        u1 = u1 / np.linalg.norm(u1)
        
        # Generate second vector orthogonal to first
        u2 = np.random.randn(5)
        # Gram-Schmidt orthogonalization
        u2 = u2 - np.dot(u2, u1) * u1
        u2 = u2 / np.linalg.norm(u2)
        
        # Verify orthogonality
        dot_product = np.dot(u1, u2)
        assert abs(dot_product) < 1e-10, f"Vectors not orthogonal: ⟨u₁,u₂⟩ = {dot_product}"
        
        self.u1 = u1
        self.u2 = u2
    
    def apply(self, v: np.ndarray) -> np.ndarray:
        """
        Apply DoubleKick operator.
        
        Args:
            v: Input vector (5D)
            
        Returns:
            Transformed vector
        """
        return v + self.alpha1 * self.u1 + self.alpha2 * self.u2
    
    def verify_non_expansive(self) -> bool:
        """
        Verify that the operator is non-expansive.
        
        Returns:
            True if non-expansive (Lipschitz ≤ 1)
        """
        # For DK to be non-expansive, we need |α₁| + |α₂| ≤ η ≪ 1
        # The Lipschitz constant is approximately 1 + η
        return self.eta <= 0.1
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get operator information.
        
        Returns:
            Dictionary with operator parameters
        """
        return {
            "alpha1": self.alpha1,
            "alpha2": self.alpha2,
            "eta": self.eta,
            "u1_u2_orthogonal": abs(np.dot(self.u1, self.u2)) < 1e-10,
            "non_expansive": self.verify_non_expansive()
        }
    
    def compute_impulse_strength(self, v: np.ndarray) -> float:
        """
        Compute the strength of impulse applied to vector.
        
        Args:
            v: Input vector
            
        Returns:
            Impulse magnitude
        """
        impulse = self.alpha1 * self.u1 + self.alpha2 * self.u2
        return float(np.linalg.norm(impulse))