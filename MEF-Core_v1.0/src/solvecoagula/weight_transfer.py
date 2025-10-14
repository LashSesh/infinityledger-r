"""
Weight-Transfer (WT) operator implementation.
Scale-based weight redistribution across micro, meso, and macro levels.
"""

import numpy as np
from typing import Dict, Any, List

class WeightTransfer:
    """
    Weight-Transfer operator redistributes weights across scales.
    WT(v) = Σ_{ℓ∈L} w'_ℓ · P_ℓ(v)
    where w'_ℓ = (1-γ)w_ℓ + γw̃_ℓ, 0 < γ ≤ 0.5
    Maintains contractivity through convex combination.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Weight-Transfer operator.
        
        Args:
            config: Configuration with gamma and levels
        """
        self.gamma = config.get('gamma', 0.1)
        self.levels = config.get('levels', ['micro', 'meso', 'macro'])
        
        # Verify gamma constraint for contractivity
        assert 0 < self.gamma <= 0.5, f"Gamma must be in (0, 0.5], got {self.gamma}"
        
        # Initialize weights for each scale
        self._initialize_weights()
        
        # Initialize projection matrices for each scale
        self._initialize_projections()
    
    def _initialize_weights(self):
        """Initialize scale weights ensuring sum to 1."""
        # Initial uniform weights
        n_levels = len(self.levels)
        self.weights = {level: 1.0 / n_levels for level in self.levels}
        
        # Target weights for transfer (slight bias towards meso scale)
        self.target_weights = {
            'micro': 0.25,
            'meso': 0.45,
            'macro': 0.30
        }
        
        # Ensure weights sum to 1
        total = sum(self.target_weights.values())
        self.target_weights = {k: v/total for k, v in self.target_weights.items()}
    
    def _initialize_projections(self):
        """Initialize scale projection matrices."""
        np.random.seed(42)  # Deterministic initialization
        
        self.projections = {}
        
        for level in self.levels:
            if level == 'micro':
                # Micro: focus on individual components
                P = np.diag([1.2, 0.8, 1.0, 0.9, 1.1])
            elif level == 'meso':
                # Meso: focus on component pairs
                P = np.array([
                    [0.7, 0.3, 0, 0, 0],
                    [0.3, 0.7, 0, 0, 0],
                    [0, 0, 0.6, 0.4, 0],
                    [0, 0, 0.4, 0.6, 0],
                    [0, 0, 0, 0, 1.0]
                ])
            else:  # macro
                # Macro: global averaging
                P = np.ones((5, 5)) / 5
                np.fill_diagonal(P, 0.4)
            
            # Normalize to ensure ||P||_2 ≤ 1
            spectral_norm = np.linalg.norm(P, ord=2)
            if spectral_norm > 1:
                P = P / spectral_norm
            
            self.projections[level] = P
    
    def update_weights(self):
        """Update weights using transfer rule w'_ℓ = (1-γ)w_ℓ + γw̃_ℓ."""
        new_weights = {}
        
        for level in self.levels:
            old_w = self.weights[level]
            target_w = self.target_weights.get(level, old_w)
            new_w = (1 - self.gamma) * old_w + self.gamma * target_w
            new_weights[level] = new_w
        
        # Normalize to ensure sum = 1
        total = sum(new_weights.values())
        self.weights = {k: v/total for k, v in new_weights.items()}
    
    def apply(self, v: np.ndarray) -> np.ndarray:
        """
        Apply Weight-Transfer operator.
        
        Args:
            v: Input vector (5D)
            
        Returns:
            Transformed vector with redistributed scale weights
        """
        # Update weights
        self.update_weights()
        
        # Apply weighted sum of scale projections
        result = np.zeros_like(v)
        
        for level in self.levels:
            P_l = self.projections[level]
            w_l = self.weights[level]
            result += w_l * (P_l @ v)
        
        return result
    
    def verify_convexity(self) -> bool:
        """
        Verify that the operator maintains convexity.
        
        Returns:
            True if weights form valid convex combination
        """
        total_weight = sum(self.weights.values())
        all_positive = all(w > 0 for w in self.weights.values())
        return abs(total_weight - 1.0) < 1e-10 and all_positive
    
    def verify_non_expansive(self) -> Dict[str, Any]:
        """
        Verify non-expansiveness of the operator.
        
        Returns:
            Verification results
        """
        # The operator is non-expansive if it's a convex combination
        # of non-expansive projections
        
        projection_norms = {}
        for level, P in self.projections.items():
            norm = np.linalg.norm(P, ord=2)
            projection_norms[level] = float(norm)
        
        # Test empirically
        np.random.seed(42)
        test_results = []
        
        for _ in range(10):
            v1 = np.random.randn(5)
            v2 = np.random.randn(5)
            
            wt_v1 = self.apply(v1)
            wt_v2 = self.apply(v2)
            
            dist_before = np.linalg.norm(v2 - v1)
            dist_after = np.linalg.norm(wt_v2 - wt_v1)
            
            if dist_before > 0:
                ratio = dist_after / dist_before
                test_results.append(float(ratio))
        
        return {
            "projection_norms": projection_norms,
            "weights_sum_to_one": self.verify_convexity(),
            "empirical_ratios": {
                "mean": float(np.mean(test_results)),
                "max": float(np.max(test_results))
            },
            "is_non_expansive": np.max(test_results) <= 1.0
        }
    
    def get_scale_contributions(self, v: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Get individual scale contributions to output.
        
        Args:
            v: Input vector
            
        Returns:
            Dictionary of scale contributions
        """
        contributions = {}
        
        for level in self.levels:
            P_l = self.projections[level]
            w_l = self.weights[level]
            contributions[level] = w_l * (P_l @ v)
        
        return contributions
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get operator information.
        
        Returns:
            Dictionary with operator parameters
        """
        return {
            "gamma": self.gamma,
            "levels": self.levels,
            "current_weights": {k: float(v) for k, v in self.weights.items()},
            "target_weights": {k: float(v) for k, v in self.target_weights.items()},
            "is_convex": self.verify_convexity(),
            "non_expansive": self.verify_non_expansive()
        }