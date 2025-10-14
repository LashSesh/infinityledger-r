"""
metatron_router.py
------------------

Metatron Cube integration as the topological routing layer for MEF-Core.
This module serves as the central routing system for all operator transformations,
providing 5040 permutation paths through the S7 symmetry group and managing
resonance calculations across the 13-node topology.
"""

import json
import uuid
import hashlib
import numpy as np
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum

# Import Metatron Cube components
from src.cube import MetatronCube
from src.graph import MetatronCubeGraph
from src.geometry import canonical_nodes, canonical_edges, Node
from src.symmetries import (
    generate_s7_permutations,
    generate_c6_subgroup,
    generate_d6_subgroup,
    permutation_matrix
)
from src.quantum import QuantumState, QuantumOperator
from src.qlogic import QLogicEngine
from src.mandorla import MandorlaField
from src.spiralmemory import SpiralMemory
from src.gabriel_cell import GabrielCell
from src.resonance_tensor import ResonanceTensorField
from src.field_vector import FieldVector


class OperatorType(Enum):
    """MEF-Core operator types that can be routed through Metatron topology."""
    DK = "DoubleKick"  # Double impulse operator
    SW = "Sweep"       # Threshold sweep operator
    PI = "PathInvariance"  # Path invariance projection
    WT = "WeightTransfer"  # Scale weight transfer


@dataclass
class RouteSpec:
    """
    Specification for a transformation route through Metatron topology.
    
    Attributes:
        route_id: Unique identifier for this route
        permutation: S7 permutation defining the route
        operator_sequence: Ordered list of operators to apply
        symmetry_group: Symmetry group used (C6, D6, S7)
        score: Route quality score based on resonance metrics
        metadata: Additional routing metadata
    """
    route_id: str
    permutation: Tuple[int, ...]
    operator_sequence: List[OperatorType]
    symmetry_group: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TransformationResult:
    """
    Result of applying a transformation through Metatron routing.
    
    Attributes:
        input_vector: Original input state
        output_vector: Transformed output state
        route_spec: Route specification used
        resonance_metrics: Resonance calculations along the path
        convergence_data: Convergence metrics for each step
        timestamp: Transformation timestamp
    """
    input_vector: np.ndarray
    output_vector: np.ndarray
    route_spec: RouteSpec
    resonance_metrics: Dict[str, float]
    convergence_data: List[Dict[str, Any]]
    timestamp: str


class MetatronRouter:
    """
    Central topological routing system for MEF-Core transformations.
    
    This router manages the complete 5040-path operator space through
    the Metatron Cube's 13-node topology, providing deterministic
    routing for all transformations in the pipeline.
    """
    
    def __init__(self,
                 seed: str = "MEF_METATRON_42",
                 full_edges: bool = True,
                 cache_routes: bool = True,
                 storage_path: str = "C:/MEF/metatron"):
        """
        Initialize the Metatron Router with full topological capabilities.
        
        Args:
            seed: Deterministic seed for reproducibility
            full_edges: Use full 78-edge connectivity if True
            cache_routes: Cache computed routes for performance
            storage_path: Path for storing route cache and metadata
        """
        self.seed = seed
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize core Metatron Cube
        self.metatron = MetatronCube(full_edges=full_edges)
        self.graph = MetatronCubeGraph(edges=canonical_edges() if not full_edges else None)
        
        # Initialize resonance and quantum components
        self.qlogic = QLogicEngine(num_nodes=13)
        self.mandorla = MandorlaField(alpha=0.5, beta=0.5)
        self.resonance_field = ResonanceTensorField(shape=(3, 3, 3))
        self.spiral = SpiralMemory(alpha=0.07)
        
        # Gabriel cells for feedback coupling
        self.gabriel_cells = [GabrielCell() for _ in range(4)]
        for i in range(3):
            self.gabriel_cells[i].couple(self.gabriel_cells[i + 1])
        
        # Generate and cache all S7 permutations
        self.s7_perms = generate_s7_permutations()
        self.c6_perms = generate_c6_subgroup()
        self.d6_perms = generate_d6_subgroup()
        
        # Route cache for performance
        self.route_cache: Dict[str, RouteSpec] = {}
        self.cache_enabled = cache_routes
        
        # Load existing cache if available
        if cache_routes:
            self._load_route_cache()
        
        # Operator implementations
        self.operators = self._initialize_operators()
        
    def _initialize_operators(self) -> Dict[OperatorType, callable]:
        """
        Initialize operator implementations for the four core MEF operators.
        
        Returns:
            Dictionary mapping operator types to implementation functions
        """
        return {
            OperatorType.DK: self._apply_double_kick,
            OperatorType.SW: self._apply_sweep,
            OperatorType.PI: self._apply_path_invariance,
            OperatorType.WT: self._apply_weight_transfer
        }
    
    def select_optimal_route(self,
                           input_state: np.ndarray,
                           target_properties: Optional[Dict[str, Any]] = None) -> RouteSpec:
        """
        Select the optimal transformation route for given input state.
        
        This method evaluates multiple routes through the S7 permutation space
        and selects the one with highest resonance score.
        
        Args:
            input_state: Input vector to transform
            target_properties: Optional target properties to optimize for
            
        Returns:
            Optimal route specification
        """
        # Generate cache key
        input_array = np.asarray(input_state, dtype=float)
        cache_key = self._generate_cache_key(input_array, target_properties)
        
        # Check cache first
        if self.cache_enabled and cache_key in self.route_cache:
            return self.route_cache[cache_key]
        
        # Pad input to 13 dimensions for Metatron operations
        padded_input = self._pad_to_metatron_dims(input_array)
        
        # Evaluate subset of S7 permutations (full 5040 is expensive)
        # In production, use heuristics to select promising candidates
        candidate_perms = self._select_candidate_permutations(padded_input)
        
        best_route = None
        best_score = -np.inf
        
        for perm in candidate_perms:
            # Generate operator sequence for this permutation
            op_sequence = self._generate_operator_sequence(perm)
            
            # Evaluate route quality
            score = self._evaluate_route(padded_input, perm, op_sequence)
            
            if score > best_score:
                best_score = score
                best_route = RouteSpec(
                    route_id=str(uuid.uuid4()),
                    permutation=perm,
                    operator_sequence=op_sequence,
                    symmetry_group=self._identify_symmetry_group(perm),
                    score=score,
                    metadata={
                        "input_hash": hashlib.sha256(input_array.tobytes()).hexdigest(),
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
        
        # Cache the result
        if self.cache_enabled and best_route:
            self.route_cache[cache_key] = best_route
            self._save_route_cache()
        
        return best_route
    
    def transform(self,
                 input_vector: np.ndarray,
                 route_spec: Optional[RouteSpec] = None) -> TransformationResult:
        """
        Apply transformation through Metatron topology using specified or optimal route.
        
        Args:
            input_vector: Input state vector
            route_spec: Specific route to use (if None, selects optimal)
            
        Returns:
            Complete transformation result with metrics
        """
        # Select route if not provided
        if route_spec is None:
            route_spec = self.select_optimal_route(input_vector)
        
        # Pad input for Metatron operations
        current_state = self._pad_to_metatron_dims(input_vector)
        
        # Apply permutation to initial state
        perm_matrix = np.asarray(permutation_matrix(route_spec.permutation), dtype=float)
        current_state = self._matrix_vector_product(perm_matrix, current_state)
        
        # Track convergence at each step
        convergence_data = []
        
        # Apply operator sequence
        for operator in route_spec.operator_sequence:
            prev_state = current_state.copy()
            
            # Apply operator through Metatron topology
            current_state = self.operators[operator](current_state)
            
            # Calculate convergence metrics
            convergence = {
                "operator": operator.value,
                "delta_norm": float(np.linalg.norm(current_state - prev_state)),
                "resonance": float(self._calculate_resonance(current_state)),
                "entropy": float(self._calculate_entropy(current_state))
            }
            convergence_data.append(convergence)
        
        # Apply inverse permutation to return to original basis
        perm_matrix_T = self._transpose_matrix(perm_matrix)
        current_state = self._matrix_vector_product(perm_matrix_T, current_state)
        
        # Calculate final resonance metrics
        resonance_metrics = self._calculate_resonance_metrics(
            input_vector, 
            current_state[:len(input_vector)]  # Truncate to original dimensions
        )
        
        return TransformationResult(
            input_vector=input_vector,
            output_vector=current_state[:len(input_vector)],
            route_spec=route_spec,
            resonance_metrics=resonance_metrics,
            convergence_data=convergence_data,
            timestamp=datetime.utcnow().isoformat()
        )
    
    def _apply_double_kick(self, state: np.ndarray) -> np.ndarray:
        """
        Apply DoubleKick operator through Metatron topology.

        The operator applies two orthogonal impulses to destabilize
        local minima while maintaining contractivity.
        """
        # Generate orthogonal impulses using Metatron geometry
        nodes = canonical_nodes()
        
        # Use hexagon and cube geometries for orthogonal directions
        hexagon_direction = np.zeros(13)
        cube_direction = np.zeros(13)
        
        for i, node in enumerate(nodes):
            if node.type == "hexagon":
                hexagon_direction[i] = node.coords[0]  # x-component
            elif node.type == "cube":
                cube_direction[i] = node.coords[1]  # y-component
        
        # Normalize directions
        if np.linalg.norm(hexagon_direction) > 0:
            hexagon_direction /= np.linalg.norm(hexagon_direction)
        if np.linalg.norm(cube_direction) > 0:
            cube_direction /= np.linalg.norm(cube_direction)
        
        # Apply double kick with small amplitudes
        alpha1, alpha2 = 0.05, -0.03
        return state + alpha1 * hexagon_direction + alpha2 * cube_direction

    def _matrix_vector_product(self, matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
        vec = np.asarray(vector, dtype=float)
        result = [np.dot(row, vec) for row in matrix]
        return np.asarray(result, dtype=float)

    def _transpose_matrix(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray(list(zip(*matrix)), dtype=float)
    
    def _apply_sweep(self, state: np.ndarray) -> np.ndarray:
        """
        Apply Sweep operator using resonance field dynamics.
        
        The operator modulates state through adaptive thresholding
        based on local resonance patterns.
        """
        # Calculate mean resonance
        self.mandorla.clear_inputs()
        
        # Add state projections at different scales
        for scale in [1.0, 0.5, 2.0]:
            scaled_state = state * scale
            self.mandorla.add_input(scaled_state[:5])  # Use first 5 dims
        
        resonance = self.mandorla.calc_resonance()
        
        # Apply threshold gate with cosine schedule
        tau = 0.5 + 0.3 * np.cos(resonance * np.pi)
        beta = 0.1
        
        # Sigmoid gate function
        gate_value = 1.0 / (1.0 + np.exp(-(np.mean(state) - tau) / beta))
        
        return gate_value * state
    
    def _apply_path_invariance(self, state: np.ndarray) -> np.ndarray:
        """
        Apply Path Invariance projection through canonical ordering.
        
        This operator ensures invariance under path reordering
        by projecting to a canonical representation.
        """
        # Apply multiple symmetry operations and average
        projections = []
        
        # Identity
        projections.append(state)
        
        # Apply C6 rotations
        for perm_dict in self.metatron.enumerate_group("C6")[:3]:
            perm_matrix = np.array(perm_dict["matrix"])
            projections.append(perm_matrix @ state)
        
        # Average all projections for invariance
        averaged = np.mean(projections, axis=0)
        
        # Sort to canonical form
        sorted_indices = np.argsort(np.abs(averaged))[::-1]
        canonical = np.zeros_like(averaged)
        canonical[sorted_indices] = np.sort(np.abs(averaged))[::-1] * np.sign(averaged[sorted_indices])
        
        return canonical
    
    def _apply_weight_transfer(self, state: np.ndarray) -> np.ndarray:
        """
        Apply Weight Transfer between topological scales.
        
        Redistributes weights across micro/meso/macro scales
        defined by the Metatron topology.
        """
        # Define scale regions based on node types
        center_idx = [0]  # Center node (macro)
        hexagon_idx = list(range(1, 7))  # Hexagon nodes (meso)
        cube_idx = list(range(7, 13))  # Cube nodes (micro)
        
        # Calculate current scale weights
        macro_weight = np.sum(np.abs(state[center_idx]))
        meso_weight = np.sum(np.abs(state[hexagon_idx]))
        micro_weight = np.sum(np.abs(state[cube_idx]))
        
        total_weight = macro_weight + meso_weight + micro_weight
        
        if total_weight > 0:
            # Transfer weights with conservation
            gamma = 0.1
            
            # Transfer from micro to meso
            transfer_micro_meso = gamma * micro_weight
            # Transfer from meso to macro
            transfer_meso_macro = gamma * meso_weight * 0.5
            
            # Apply transfers
            new_state = state.copy()
            
            # Adjust micro scale
            if micro_weight > 0:
                new_state[cube_idx] *= (1 - gamma)
            
            # Adjust meso scale
            if meso_weight > 0:
                adjustment = (1 - gamma * 0.5) + (transfer_micro_meso / (meso_weight + 1e-10))
                new_state[hexagon_idx] *= adjustment
            
            # Adjust macro scale
            if macro_weight > 0:
                adjustment = 1 + (transfer_meso_macro / (macro_weight + 1e-10))
                new_state[center_idx] *= adjustment
            else:
                for idx in center_idx:
                    new_state[idx] = new_state[idx] + transfer_meso_macro
            
            return new_state
        
        return state
    
    def _pad_to_metatron_dims(self, vector: np.ndarray) -> np.ndarray:
        """
        Pad vector to 13 dimensions for Metatron operations.
        
        Args:
            vector: Input vector of arbitrary dimension
            
        Returns:
            13-dimensional vector suitable for Metatron operations
        """
        if len(vector) >= 13:
            return vector[:13]
        
        padded = np.zeros(13)
        padded[:len(vector)] = vector
        return padded
    
    def _select_candidate_permutations(self, 
                                      input_state: np.ndarray,
                                      n_candidates: int = 10) -> List[Tuple[int, ...]]:
        """
        Select promising permutation candidates using heuristics.
        
        Args:
            input_state: Input state vector
            n_candidates: Number of candidates to evaluate
            
        Returns:
            List of candidate permutations
        """
        # Use resonance-based heuristic to select candidates
        candidates = []
        
        # Always include identity
        candidates.append(tuple(range(1, 14)))
        
        # Include C6 and D6 subgroups (more structured)
        for perm in self.c6_perms[:min(3, n_candidates - 1)]:
            # Extend to full 13-element permutation
            extended = tuple(list(perm) + list(range(8, 14)))
            candidates.append(extended)
        
        for perm in self.d6_perms[:min(3, n_candidates - len(candidates))]:
            extended = tuple(list(perm) + list(range(8, 14)))
            candidates.append(extended)
        
        # Add random samples from S7 if needed
        if len(candidates) < n_candidates:
            # Use deterministic sampling based on input hash
            np.random.seed(int(hashlib.sha256(input_state.tobytes()).hexdigest()[:8], 16) % 2**32)
            indices = np.random.choice(len(self.s7_perms), 
                                     min(n_candidates - len(candidates), len(self.s7_perms)),
                                     replace=False)
            for idx in indices:
                perm = self.s7_perms[idx]
                extended = tuple(list(perm) + list(range(8, 14)))
                candidates.append(extended)
        
        return candidates[:n_candidates]
    
    def _generate_operator_sequence(self, 
                                   permutation: Tuple[int, ...]) -> List[OperatorType]:
        """
        Generate operator sequence based on permutation properties.
        
        Args:
            permutation: S7 permutation
            
        Returns:
            Ordered list of operators to apply
        """
        # Calculate permutation signature to determine sequence
        signature = sum(permutation) % 4
        
        sequences = [
            [OperatorType.DK, OperatorType.SW, OperatorType.PI, OperatorType.WT],
            [OperatorType.SW, OperatorType.DK, OperatorType.WT, OperatorType.PI],
            [OperatorType.PI, OperatorType.WT, OperatorType.DK, OperatorType.SW],
            [OperatorType.WT, OperatorType.PI, OperatorType.SW, OperatorType.DK]
        ]
        
        return sequences[signature]
    
    def _evaluate_route(self,
                       input_state: np.ndarray,
                       permutation: Tuple[int, ...],
                       operator_sequence: List[OperatorType]) -> float:
        """
        Evaluate quality score for a specific route.
        
        Args:
            input_state: Input state vector
            permutation: Permutation to apply
            operator_sequence: Operator sequence
            
        Returns:
            Quality score for the route
        """
        # Apply permutation
        perm_matrix = permutation_matrix(permutation)
        current = perm_matrix @ input_state
        
        # Track metrics through transformation
        total_convergence = 0.0
        total_resonance = 0.0
        
        for operator in operator_sequence:
            prev = current.copy()
            current = self.operators[operator](current)
            
            # Measure convergence
            convergence = 1.0 / (1.0 + np.linalg.norm(current - prev))
            total_convergence += convergence
            
            # Measure resonance
            resonance = self._calculate_resonance(current)
            total_resonance += resonance
        
        # Combine metrics for overall score
        score = (total_convergence / len(operator_sequence)) * \
                (total_resonance / len(operator_sequence))
        
        return float(score)
    
    def _calculate_resonance(self, state: np.ndarray) -> float:
        """
        Calculate resonance metric for a state vector.
        
        Args:
            state: State vector
            
        Returns:
            Resonance value in [0, 1]
        """
        # Use QLOGIC spectral analysis
        qlogic_result = self.qlogic.step(t=0)
        spectrum = qlogic_result["spectrum"]
        
        # Calculate spectral coherence
        if len(spectrum) > 0:
            # Normalize spectrum
            spectrum_norm = spectrum / (np.sum(spectrum) + 1e-10)
            # Calculate entropy (lower = more coherent)
            entropy = -np.sum(spectrum_norm * np.log(spectrum_norm + 1e-10))
            # Map to resonance (high coherence = high resonance)
            max_entropy = np.log(len(spectrum))
            resonance = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 1.0
        else:
            resonance = 0.0
        
        return float(np.clip(resonance, 0, 1))
    
    def _calculate_entropy(self, state: np.ndarray) -> float:
        """
        Calculate entropy of state vector.
        
        Args:
            state: State vector
            
        Returns:
            Entropy value
        """
        # Normalize to probability distribution
        probs = np.abs(state)
        probs = probs / (np.sum(probs) + 1e-10)
        
        # Calculate Shannon entropy
        entropy = -np.sum(probs * np.log(probs + 1e-10))
        
        return float(entropy)
    
    def _calculate_resonance_metrics(self,
                                    input_vector: np.ndarray,
                                    output_vector: np.ndarray) -> Dict[str, float]:
        """
        Calculate comprehensive resonance metrics for transformation.
        
        Args:
            input_vector: Original input
            output_vector: Transformed output
            
        Returns:
            Dictionary of resonance metrics
        """
        # Input/output resonance
        input_resonance = self._calculate_resonance(self._pad_to_metatron_dims(input_vector))
        output_resonance = self._calculate_resonance(self._pad_to_metatron_dims(output_vector))
        
        # Coherence using Mandorla field
        self.mandorla.clear_inputs()
        self.mandorla.add_input(input_vector[:5] if len(input_vector) >= 5 else np.pad(input_vector, (0, 5 - len(input_vector))))
        self.mandorla.add_input(output_vector[:5] if len(output_vector) >= 5 else np.pad(output_vector, (0, 5 - len(output_vector))))
        coherence = self.mandorla.calc_resonance()
        
        # Stability (inverse of change magnitude)
        stability = 1.0 / (1.0 + np.linalg.norm(output_vector - input_vector))
        
        # Convergence (reduction in entropy)
        input_entropy = self._calculate_entropy(self._pad_to_metatron_dims(input_vector))
        output_entropy = self._calculate_entropy(self._pad_to_metatron_dims(output_vector))
        convergence = max(0, (input_entropy - output_entropy) / (input_entropy + 1e-10))
        
        return {
            "input_resonance": float(input_resonance),
            "output_resonance": float(output_resonance),
            "coherence": float(coherence),
            "stability": float(stability),
            "convergence": float(convergence)
        }
    
    def _identify_symmetry_group(self, permutation: Tuple[int, ...]) -> str:
        """
        Identify which symmetry group a permutation belongs to.
        
        Args:
            permutation: Permutation tuple
            
        Returns:
            Name of symmetry group (C6, D6, S7, or Unknown)
        """
        # Check if it's identity
        if permutation == tuple(range(1, 14)):
            return "Identity"
        
        # Check C6 membership
        for c6_perm in self.c6_perms:
            extended = tuple(list(c6_perm) + list(range(8, 14)))
            if extended == permutation:
                return "C6"
        
        # Check D6 membership
        for d6_perm in self.d6_perms:
            extended = tuple(list(d6_perm) + list(range(8, 14)))
            if extended == permutation:
                return "D6"
        
        # Otherwise it's from general S7
        return "S7"
    
    def _generate_cache_key(self, 
                           input_state: np.ndarray,
                           target_properties: Optional[Dict[str, Any]]) -> str:
        """
        Generate cache key for route lookup.
        
        Args:
            input_state: Input vector
            target_properties: Target properties
            
        Returns:
            Cache key string
        """
        # Hash input state
        state_array = np.asarray(input_state, dtype=float)
        state_bytes = state_array.tobytes() if hasattr(state_array, "tobytes") else bytes(
            str(state_array), "utf-8"
        )
        state_hash = hashlib.sha256(state_bytes).hexdigest()[:16]
        
        # Hash target properties if provided
        if target_properties:
            prop_str = json.dumps(target_properties, sort_keys=True)
            prop_hash = hashlib.sha256(prop_str.encode()).hexdigest()[:16]
        else:
            prop_hash = "none"
        
        return f"{state_hash}_{prop_hash}"
    
    def _load_route_cache(self):
        """Load route cache from disk if available."""
        cache_file = self.storage_path / "route_cache.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    
                # Reconstruct RouteSpec objects
                for key, route_data in cache_data.items():
                    self.route_cache[key] = RouteSpec(
                        route_id=route_data["route_id"],
                        permutation=tuple(route_data["permutation"]),
                        operator_sequence=[OperatorType[op] for op in route_data["operator_sequence"]],
                        symmetry_group=route_data["symmetry_group"],
                        score=route_data["score"],
                        metadata=route_data.get("metadata", {})
                    )
            except Exception as e:
                print(f"Failed to load route cache: {e}")
    
    def _save_route_cache(self):
        """Save route cache to disk."""
        cache_file = self.storage_path / "route_cache.json"
        
        try:
            # Convert RouteSpec objects to JSON-serializable format
            cache_data = {}
            for key, route in self.route_cache.items():
                cache_data[key] = {
                    "route_id": route.route_id,
                    "permutation": list(route.permutation),
                    "operator_sequence": [op.name for op in route.operator_sequence],
                    "symmetry_group": route.symmetry_group,
                    "score": route.score,
                    "metadata": route.metadata
                }
            
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            print(f"Failed to save route cache: {e}")
    
    def get_topology_metrics(self) -> Dict[str, Any]:
        """
        Get current topology metrics and router status.
        
        Returns:
            Dictionary of topology metrics
        """
        adjacency = self.graph.get_adjacency_matrix()
        
        return {
            "nodes": 13,
            "edges": int(np.sum(adjacency) / 2),  # Undirected edges
            "s7_permutations": len(self.s7_perms),
            "c6_subgroup": len(self.c6_perms),
            "d6_subgroup": len(self.d6_perms),
            "cached_routes": len(self.route_cache),
            "cache_enabled": self.cache_enabled,
            "full_connectivity": self.metatron.edges == list(canonical_edges())
        }
    
    def export_route_graph(self, route_spec: RouteSpec, format: str = "json") -> str:
        """
        Export route visualization in specified format.
        
        Args:
            route_spec: Route to export
            format: Export format (json or dot)
            
        Returns:
            Exported route representation
        """
        if format == "json":
            return json.dumps({
                "route_id": route_spec.route_id,
                "permutation": list(route_spec.permutation),
                "operators": [op.value for op in route_spec.operator_sequence],
                "symmetry": route_spec.symmetry_group,
                "score": route_spec.score,
                "metadata": route_spec.metadata
            }, indent=2)
        
        elif format == "dot":
            # GraphViz DOT format for visualization
            lines = ["digraph MetatronRoute {"]
            lines.append(f'  label="Route {route_spec.route_id[:8]}... Score: {route_spec.score:.3f}";')
            
            # Add nodes for each step
            lines.append('  rankdir=LR;')
            lines.append('  node [shape=box];')
            
            # Initial state
            lines.append('  "Input" [shape=circle];')
            
            # Operator nodes
            for i, op in enumerate(route_spec.operator_sequence):
                lines.append(f'  "Op{i}" [label="{op.value}"];')
            
            # Output state
            lines.append('  "Output" [shape=doublecircle];')
            
            # Add edges
            if route_spec.operator_sequence:
                lines.append('  "Input" -> "Op0";')
                for i in range(len(route_spec.operator_sequence) - 1):
                    lines.append(f'  "Op{i}" -> "Op{i+1}";')
                lines.append(f'  "Op{len(route_spec.operator_sequence)-1}" -> "Output";')
            else:
                lines.append('  "Input" -> "Output";')
            
            lines.append("}")
            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")