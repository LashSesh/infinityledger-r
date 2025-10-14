"""
Pfadinvarianz (PI) operator implementation.
Path invariance projection ensuring canonical ordering.
"""

import numpy as np
from typing import Dict, Any, List, Callable
import itertools

class Pfadinvarianz:
    """
    Pfadinvarianz operator enforces path equivalence through projection.
    PI(v) = (1/|Π|) Σ_{p∈Π} T_p(v) with canonical ordering.
    Properties: idempotent, non-expansive projection.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Pfadinvarianz operator.
        
        Args:
            config: Configuration with canon type and tolerance
        """
        self.canon = config.get('canon', 'lexicographic')
        self.tol = config.get('tol', 1e-6)
        
        # Define permutation operations for path equivalence
        self._initialize_permutations()
    
    def _initialize_permutations(self):
        """Initialize the set of path-equivalent operations."""
        # For 5D vectors, we consider a subset of permutations
        # that maintain certain invariants
        
        # Define base permutations (not all 5! = 120 permutations)
        # Use cyclic permutations and reflections for efficiency
        self.permutations = [
            [0, 1, 2, 3, 4],  # Identity
            [1, 2, 3, 4, 0],  # Cyclic shift right
            [4, 0, 1, 2, 3],  # Cyclic shift left
            [0, 2, 4, 1, 3],  # Even-odd separation
            [1, 3, 0, 4, 2],  # Alternating
            [4, 3, 2, 1, 0],  # Reversal
        ]
        
        # Convert to numpy arrays for efficiency
        self.permutations = [np.array(p) for p in self.permutations]
    
    def apply_permutation(self, v: np.ndarray, perm: np.ndarray) -> np.ndarray:
        """
        Apply a permutation to vector.
        
        Args:
            v: Input vector
            perm: Permutation indices
            
        Returns:
            Permuted vector
        """
        return v[perm]
    
    def canonical_order(self, vectors: List[np.ndarray]) -> List[np.ndarray]:
        """
        Sort vectors in canonical order based on specified criterion.
        
        Args:
            vectors: List of vectors
            
        Returns:
            Canonically ordered list
        """
        if self.canon == 'lexicographic':
            # Sort lexicographically
            return sorted(vectors, key=lambda v: tuple(v))
        elif self.canon == 'norm':
            # Sort by norm
            return sorted(vectors, key=lambda v: np.linalg.norm(v))
        elif self.canon == 'sum':
            # Sort by sum of components
            return sorted(vectors, key=lambda v: np.sum(v))
        else:
            # Default: return as is
            return vectors
    
    def apply(self, v: np.ndarray) -> np.ndarray:
        """
        Apply Pfadinvarianz operator.
        
        Args:
            v: Input vector (5D)
            
        Returns:
            Projected vector ensuring path invariance
        """
        # Generate all path-equivalent vectors
        path_vectors = []
        for perm in self.permutations:
            permuted = self.apply_permutation(v, perm)
            path_vectors.append(permuted)
        
        # Apply canonical ordering
        ordered_vectors = self.canonical_order(path_vectors)
        
        # Average over path-equivalent operations
        result = np.mean(ordered_vectors, axis=0)
        
        return result
    
    def verify_idempotence(self, v: np.ndarray) -> bool:
        """
        Verify that PI(PI(v)) = PI(v) (idempotence property).
        
        Args:
            v: Test vector
            
        Returns:
            True if idempotent within tolerance
        """
        pi_v = self.apply(v)
        pi_pi_v = self.apply(pi_v)
        
        difference = np.linalg.norm(pi_pi_v - pi_v)
        return difference < self.tol
    
    def verify_non_expansive(self) -> Dict[str, Any]:
        """
        Verify non-expansiveness of the projection.
        
        Returns:
            Verification results
        """
        # Test with random vector pairs
        np.random.seed(42)
        test_results = []
        
        for _ in range(10):
            v1 = np.random.randn(5)
            v2 = np.random.randn(5)
            
            pi_v1 = self.apply(v1)
            pi_v2 = self.apply(v2)
            
            dist_before = np.linalg.norm(v2 - v1)
            dist_after = np.linalg.norm(pi_v2 - pi_v1)
            
            if dist_before > 0:
                ratio = dist_after / dist_before
                test_results.append(float(ratio))
        
        return {
            "mean_ratio": float(np.mean(test_results)),
            "max_ratio": float(np.max(test_results)),
            "is_non_expansive": np.max(test_results) <= 1.0 + self.tol
        }
    
    def compute_path_deviation(self, v: np.ndarray) -> float:
        """
        Compute path invariance deviation metric.
        
        Args:
            v: Input vector
            
        Returns:
            Deviation from perfect path invariance
        """
        # Generate all path-equivalent vectors
        path_vectors = []
        for perm in self.permutations:
            permuted = self.apply_permutation(v, perm)
            path_vectors.append(permuted)
        
        # Compute pairwise distances
        deviations = []
        for i in range(len(path_vectors)):
            for j in range(i+1, len(path_vectors)):
                dist = np.linalg.norm(path_vectors[i] - path_vectors[j])
                deviations.append(dist)
        
        return float(np.mean(deviations)) if deviations else 0.0
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get operator information.
        
        Returns:
            Dictionary with operator parameters
        """
        # Test vector for verification
        test_v = np.array([1.0, 0.5, -0.3, 0.8, -0.2])
        
        return {
            "canon": self.canon,
            "tolerance": self.tol,
            "num_permutations": len(self.permutations),
            "is_idempotent": self.verify_idempotence(test_v),
            "non_expansive": self.verify_non_expansive(),
            "test_deviation": self.compute_path_deviation(test_v)
        }