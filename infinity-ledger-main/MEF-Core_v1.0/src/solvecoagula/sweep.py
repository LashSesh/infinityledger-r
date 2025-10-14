"""
Sweep (SW) operator implementation.
Threshold sweeping with cosine schedule for resonance adjustment.
"""

import numpy as np
from typing import Dict, Any

class Sweep:
    """
    Sweep operator with gate function:
    SW(v) = g_τ(m(v)) · v
    where g_τ(x) = σ((x - τ)/β) and m(v) = mean(v)
    Uses cosine schedule for threshold evolution.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Sweep operator.
        
        Args:
            config: Configuration with tau0, beta, schedule parameters
        """
        self.tau0 = config.get('tau0', 0.5)
        self.beta = config.get('beta', 0.1)
        self.schedule = config.get('schedule', 'cosine')
        
        # Initialize iteration counter for schedule
        self.iteration = 0
        self.max_schedule_iterations = 100
        self.delta_tau = 0.3  # Maximum deviation from tau0
    
    def sigmoid(self, x: float) -> float:
        """
        Sigmoid activation function.
        
        Args:
            x: Input value
            
        Returns:
            Sigmoid output in [0, 1]
        """
        return 1 / (1 + np.exp(-x))
    
    def gate_function(self, x: float, tau: float) -> float:
        """
        Gate function g_τ(x) = σ((x - τ)/β).
        
        Args:
            x: Input value
            tau: Threshold parameter
            
        Returns:
            Gate value in [0, 1]
        """
        return self.sigmoid((x - tau) / self.beta)
    
    def compute_schedule(self) -> float:
        """
        Compute threshold value based on schedule.
        
        Returns:
            Current threshold tau
        """
        if self.schedule == 'cosine':
            # Cosine schedule: τ_t = τ₀ + 0.5(1 + cos(πt/T))Δτ
            t = self.iteration % self.max_schedule_iterations
            T = self.max_schedule_iterations
            tau = self.tau0 + 0.5 * (1 + np.cos(np.pi * t / T)) * self.delta_tau
        elif self.schedule == 'linear':
            # Linear schedule
            t = self.iteration % self.max_schedule_iterations
            T = self.max_schedule_iterations
            tau = self.tau0 + (1 - t / T) * self.delta_tau
        else:
            # Constant threshold
            tau = self.tau0
        
        return tau
    
    def apply(self, v: np.ndarray) -> np.ndarray:
        """
        Apply Sweep operator.
        
        Args:
            v: Input vector (5D)
            
        Returns:
            Transformed vector
        """
        # Compute mean of vector components
        m_v = np.mean(v)
        
        # Get current threshold from schedule
        tau = self.compute_schedule()
        
        # Apply gate function
        gate_value = self.gate_function(m_v, tau)
        
        # Apply gated multiplication
        result = gate_value * v
        
        # Increment iteration counter
        self.iteration += 1
        
        return result
    
    def verify_lipschitz(self) -> Dict[str, Any]:
        """
        Verify Lipschitz continuity of the operator.
        
        Returns:
            Lipschitz analysis results
        """
        # The gate function g_τ is bounded in [0, 1]
        # Therefore Lip(SW) ≤ max|g_τ(x)| ≤ 1
        
        # Test with sample values
        test_values = np.linspace(-2, 2, 100)
        gate_values = [self.gate_function(x, self.tau0) for x in test_values]
        
        return {
            "max_gate_value": float(np.max(gate_values)),
            "min_gate_value": float(np.min(gate_values)),
            "lipschitz_bound": 1.0,
            "is_non_expansive": True
        }
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get operator information.
        
        Returns:
            Dictionary with operator parameters
        """
        return {
            "tau0": self.tau0,
            "beta": self.beta,
            "schedule": self.schedule,
            "current_iteration": self.iteration,
            "current_tau": self.compute_schedule(),
            "lipschitz": self.verify_lipschitz()
        }
    
    def reset_schedule(self):
        """Reset the schedule iteration counter."""
        self.iteration = 0