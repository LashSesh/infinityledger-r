"""
mef_core_pipeline.py
--------------------

MEF-Core pipeline with integrated Metatron Cube topological routing.
This module orchestrates the complete transformation pipeline with
Metatron Router serving as the central routing system between
Spiral storage and Solve-Coagula operations.
"""

import json
import uuid
import hashlib
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

# Import Metatron Router
from src.topology.metatron_router import (
    MetatronRouter,
    RouteSpec,
    TransformationResult,
    OperatorType
)

# Import MEF-Core components (assuming these exist in MEF-Core)
# These would be the actual MEF-Core modules
from src.spiral.storage import SpiralStorage
from src.ingestion.triton import TritonNormalizer
from src.acquisition.adapters import AcquisitionAdapter


@dataclass
class SpiralSnapshot:
    """Spiral snapshot with Metatron routing metadata."""
    id: str
    timestamp: str
    seed: str
    phase: float
    coordinates: List[float]  # 5D coordinates
    sigma: Dict[str, float]   # psi, rho, omega
    metrics: Dict[str, Any]
    metatron_route: Optional[RouteSpec] = None
    hdag_node: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


@dataclass
class TICCandidate:
    """Temporal Information Crystal candidate with routing history."""
    tic_id: str
    seed: str
    fixpoint: List[float]
    window: Tuple[str, str]  # [t0, t1] ISO-8601
    invariants: Dict[str, float]
    sigma_bar: Dict[str, float]
    proof: Dict[str, Any]
    source_snapshot: str
    metatron_route: RouteSpec
    operator_sequence: List[str]
    transformation_metrics: Dict[str, float]


class MEFCorePipeline:
    """
    Complete MEF-Core pipeline with Metatron Cube topological routing.
    
    Data flow:
    Acquisition → Ingestion/Triton → Spiral/5D → Metatron Router → 
    Solve-Coagula → Merkaba Gate → TIC → HDAG → Ledger
    """
    
    def __init__(self,
                 seed: str = "MEF_CORE_42",
                 storage_path: str = "C:/MEF/store",
                 ledger_path: str = "C:/MEF/ledger",
                 metatron_cache: bool = True):
        """
        Initialize MEF-Core pipeline with Metatron routing.
        
        Args:
            seed: Master seed for deterministic operations
            storage_path: Path for Spiral storage
            ledger_path: Path for MEF ledger
            metatron_cache: Enable Metatron route caching
        """
        self.seed = seed
        self.storage_path = Path(storage_path)
        self.ledger_path = Path(ledger_path)
        
        # Ensure paths exist
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.ledger_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize pipeline components
        self.metatron_router = MetatronRouter(
            seed=seed,
            full_edges=True,
            cache_routes=metatron_cache,
            storage_path=str(self.storage_path / "metatron")
        )
        
        # Spiral storage for 5D snapshots
        self.spiral_storage = SpiralStorage(
            path=str(self.storage_path / "spiral"),
            dimensions=5
        )
        
        # Triton normalizer for ingestion
        self.triton = TritonNormalizer()
        
        # Solve-Coagula parameters
        self.solve_coagula_params = {
            "lambda": 0.8,      # Contraction factor
            "epsilon": 1e-6,    # Convergence threshold
            "max_iter": 1000    # Maximum iterations
        }
        
        # Track pipeline metrics
        self.metrics = {
            "snapshots_processed": 0,
            "tics_generated": 0,
            "routes_cached": 0,
            "average_convergence_time": 0.0
        }
    
    def process(self, 
                raw_input: Any,
                input_type: str = "json",
                target_properties: Optional[Dict[str, Any]] = None) -> TICCandidate:
        """
        Process raw input through complete MEF-Core pipeline with Metatron routing.
        
        Args:
            raw_input: Raw input data
            input_type: Type of input (json, text, binary, etc.)
            target_properties: Optional target properties for optimization
            
        Returns:
            TIC candidate ready for Merkaba Gate validation
        """
        # Step 1: Acquisition and Normalization
        acquired_data = self._acquire(raw_input, input_type)
        
        # Step 2: Ingestion through Triton
        normalized_data = self.triton.normalize(acquired_data)
        
        # Step 3: Create Spiral snapshot
        snapshot = self._create_spiral_snapshot(normalized_data)
        
        # Step 4: Select optimal route through Metatron topology
        route_spec = self.metatron_router.select_optimal_route(
            snapshot.coordinates,
            target_properties
        )
        
        # Store route in snapshot
        snapshot.metatron_route = route_spec
        
        # Step 5: Apply Solve-Coagula through Metatron routing
        tic_candidate = self._solve_coagula_with_routing(snapshot, route_spec)
        
        # Update metrics
        self.metrics["snapshots_processed"] += 1
        self.metrics["tics_generated"] += 1
        if route_spec.metadata.get("cached", False):
            self.metrics["routes_cached"] += 1
        
        return tic_candidate
    
    def _acquire(self, raw_input: Any, input_type: str) -> Dict[str, Any]:
        """
        Acquire and structure raw input data.
        
        Args:
            raw_input: Raw input
            input_type: Input type identifier
            
        Returns:
            Structured acquisition result
        """
        # Simple acquisition logic - in production, use proper adapters
        if input_type == "json":
            if isinstance(raw_input, str):
                data = json.loads(raw_input)
            else:
                data = raw_input
        elif input_type == "text":
            data = {"content": str(raw_input), "type": "text"}
        elif input_type == "binary":
            data = {"data": raw_input, "type": "binary"}
        else:
            data = {"raw": raw_input, "type": input_type}
        
        return {
            "data": data,
            "metadata": {
                "acquired_at": datetime.utcnow().isoformat(),
                "input_type": input_type,
                "size": len(str(raw_input))
            }
        }
    
    def _create_spiral_snapshot(self, normalized_data: Dict[str, Any]) -> SpiralSnapshot:
        """
        Create 5D Spiral snapshot from normalized data.
        
        Args:
            normalized_data: Normalized data from Triton
            
        Returns:
            Spiral snapshot with embedded coordinates
        """
        # Generate deterministic coordinates from data
        data_hash = hashlib.sha256(
            json.dumps(normalized_data, sort_keys=True).encode()
        ).hexdigest()
        
        # Use hash to seed coordinate generation
        np.random.seed(int(data_hash[:8], 16) % 2**32)
        
        # Generate 5D coordinates using spiral embedding
        theta = np.random.uniform(0, 2 * np.pi)
        r = 1.0
        a, b, c = 0.05, 0.2, 0.2
        k = 2
        
        coordinates = [
            r * np.cos(theta),
            r * np.sin(theta),
            a * theta,
            b * np.sin(k * theta),
            c * np.cos(k * theta)
        ]
        
        # Calculate sigma (psi, rho, omega)
        sigma = {
            "psi": float(np.random.uniform(0.5, 1.0)),   # Activation level
            "rho": float(np.random.uniform(0.3, 0.8)),   # Coherence
            "omega": float(np.random.uniform(0.1, 0.5))  # Rhythm
        }
        
        # Create snapshot
        snapshot = SpiralSnapshot(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            seed=self.seed,
            phase=theta,
            coordinates=coordinates,
            sigma=sigma,
            metrics={
                "resonance": sigma["psi"] * sigma["rho"],
                "stability": sigma["rho"] * sigma["omega"],
                "por": "pending"  # Will be validated later
            },
            payload=normalized_data
        )
        
        # Store in Spiral storage
        self.spiral_storage.store(snapshot.id, asdict(snapshot))
        
        return snapshot
    
    def _solve_coagula_with_routing(self,
                                   snapshot: SpiralSnapshot,
                                   route_spec: RouteSpec) -> TICCandidate:
        """
        Apply Solve-Coagula operators through Metatron routing.
        
        This method integrates the Metatron Router with the traditional
        Solve-Coagula contraction process, using the selected route
        to guide the transformation.
        
        Args:
            snapshot: Spiral snapshot to transform
            route_spec: Metatron route specification
            
        Returns:
            TIC candidate with transformation history
        """
        # Start with snapshot coordinates as initial state
        current_state = np.array(snapshot.coordinates)
        
        # Apply Metatron transformation
        transformation_result = self.metatron_router.transform(
            current_state,
            route_spec
        )
        
        # Apply additional Solve-Coagula iterations for convergence
        fixpoint = self._iterate_to_fixpoint(
            transformation_result.output_vector,
            route_spec
        )
        
        # Calculate invariants
        invariants = self._calculate_invariants(fixpoint, snapshot.coordinates)
        
        # Create TIC candidate
        tic_candidate = TICCandidate(
            tic_id=str(uuid.uuid4()),
            seed=snapshot.seed,
            fixpoint=fixpoint.tolist(),
            window=(
                snapshot.timestamp,
                datetime.utcnow().isoformat()
            ),
            invariants=invariants,
            sigma_bar={
                "psi": (snapshot.sigma["psi"] + 1.0) / 2,
                "rho": (snapshot.sigma["rho"] + 1.0) / 2,
                "omega": (snapshot.sigma["omega"] + 1.0) / 2
            },
            proof={
                "por": self._validate_resonance(fixpoint),
                "pi_gap": invariants.get("pi_gap", 0.0),
                "mci": None  # Will be calculated by Merkaba Gate if needed
            },
            source_snapshot=snapshot.id,
            metatron_route=route_spec,
            operator_sequence=[op.name for op in route_spec.operator_sequence],
            transformation_metrics=transformation_result.resonance_metrics
        )
        
        return tic_candidate
    
    def _iterate_to_fixpoint(self,
                           initial_state: np.ndarray,
                           route_spec: RouteSpec) -> np.ndarray:
        """
        Iterate Solve-Coagula to reach fixpoint.
        
        Args:
            initial_state: Starting state from Metatron transformation
            route_spec: Route specification for operator guidance
            
        Returns:
            Converged fixpoint vector
        """
        lambda_factor = self.solve_coagula_params["lambda"]
        epsilon = self.solve_coagula_params["epsilon"]
        max_iter = self.solve_coagula_params["max_iter"]
        
        # Create weight matrix based on route permutation
        n = len(initial_state)
        W = np.eye(n) * 0.5  # Base identity scaling
        
        # Add permutation influence
        perm_matrix = np.eye(13)
        for i, j in enumerate(route_spec.permutation[:n]):
            if j - 1 < n:  # Adjust for 1-based indexing
                W[i, j - 1] = W[i, j - 1] + 0.3
        
        # Normalize for contraction
        W = W / np.linalg.norm(W) * 0.9
        
        # Small bias vector
        b = np.ones(n) * 0.01
        
        # Iterate to fixpoint
        current = initial_state.copy()
        for iteration in range(max_iter):
            prev = current.copy()
            
            # Contraction mapping
            current = lambda_factor * (W @ current + b)
            
            # Check convergence
            if np.linalg.norm(current - prev) < epsilon:
                break
        
        return current
    
    def _calculate_invariants(self,
                            fixpoint: np.ndarray,
                            initial_coords: List[float]) -> Dict[str, float]:
        """
        Calculate transformation invariants.
        
        Args:
            fixpoint: Converged fixpoint
            initial_coords: Initial coordinates
            
        Returns:
            Dictionary of invariant metrics
        """
        initial = np.array(initial_coords)
        
        # Variance preservation
        variance = float(np.var(fixpoint) / (np.var(initial) + 1e-10))
        
        # Information retention
        retention = float(np.dot(fixpoint, initial) / 
                         (np.linalg.norm(fixpoint) * np.linalg.norm(initial) + 1e-10))
        
        # Spectral gap (using simple eigenvalue approximation)
        if len(fixpoint) >= 2:
            # Construct simple Laplacian
            L = np.diag(np.ones(len(fixpoint))) - np.ones((len(fixpoint), len(fixpoint))) / len(fixpoint)
            eigenvalues = np.linalg.eigvalsh(L)
            eigenvalues.sort()
            gap = float(eigenvalues[1] - eigenvalues[0]) if len(eigenvalues) > 1 else 0.0
        else:
            gap = 0.0
        
        # Path invariance gap (simplified)
        pi_gap = float(np.std(fixpoint))
        
        return {
            "variance": variance,
            "retention": abs(retention),
            "gap": gap,
            "pi_gap": pi_gap
        }
    
    def _validate_resonance(self, state: np.ndarray) -> str:
        """
        Validate Proof of Resonance for state.
        
        Args:
            state: State vector to validate
            
        Returns:
            "valid" or "invalid"
        """
        # Pad to Metatron dimensions
        padded = self.metatron_router._pad_to_metatron_dims(state)
        
        # Calculate resonance using Metatron components
        resonance = self.metatron_router._calculate_resonance(padded)
        
        # Check spectral properties
        fft = np.fft.fft(padded)
        spectral_peak = np.max(np.abs(fft))
        spectral_mean = np.mean(np.abs(fft))
        
        # Validation criteria
        if resonance > 0.5 and spectral_peak / (spectral_mean + 1e-10) > 2.0:
            return "valid"
        else:
            return "invalid"
    
    def get_pipeline_metrics(self) -> Dict[str, Any]:
        """
        Get current pipeline metrics.
        
        Returns:
            Dictionary of pipeline metrics
        """
        topology_metrics = self.metatron_router.get_topology_metrics()
        
        return {
            "pipeline": self.metrics,
            "metatron_topology": topology_metrics,
            "storage": {
                "spiral_snapshots": self.spiral_storage.count(),
                "storage_path": str(self.storage_path),
                "ledger_path": str(self.ledger_path)
            },
            "solve_coagula": self.solve_coagula_params
        }


class SpiralStorage:
    """Simple Spiral storage implementation for 5D snapshots."""
    
    def __init__(self, path: str, dimensions: int = 5):
        """
        Initialize Spiral storage.
        
        Args:
            path: Storage path
            dimensions: Number of dimensions (default 5)
        """
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.dimensions = dimensions
        self.index_file = self.path / "index.json"
        self._load_index()
    
    def _load_index(self):
        """Load storage index."""
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
        else:
            self.index = {"snapshots": {}, "count": 0}
    
    def _save_index(self):
        """Save storage index."""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def store(self, snapshot_id: str, snapshot_data: Dict[str, Any]):
        """
        Store snapshot in Spiral storage.
        
        Args:
            snapshot_id: Snapshot identifier
            snapshot_data: Snapshot data dictionary
        """
        # Store snapshot file
        snapshot_file = self.path / f"{snapshot_id}.json"
        with open(snapshot_file, 'w') as f:
            json.dump(snapshot_data, f, indent=2)
        
        # Update index
        self.index["snapshots"][snapshot_id] = {
            "file": str(snapshot_file),
            "timestamp": snapshot_data.get("timestamp"),
            "phase": snapshot_data.get("phase")
        }
        self.index["count"] = len(self.index["snapshots"])
        self._save_index()
    
    def retrieve(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve snapshot from storage.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Snapshot data or None if not found
        """
        if snapshot_id in self.index["snapshots"]:
            snapshot_file = Path(self.index["snapshots"][snapshot_id]["file"])
            if snapshot_file.exists():
                with open(snapshot_file, 'r') as f:
                    return json.load(f)
        return None
    
    def count(self) -> int:
        """Get count of stored snapshots."""
        return self.index["count"]


class TritonNormalizer:
    """Simple Triton normalizer for data ingestion."""
    
    def normalize(self, acquired_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize acquired data for Spiral embedding.
        
        Args:
            acquired_data: Data from acquisition layer
            
        Returns:
            Normalized data dictionary
        """
        data = acquired_data.get("data", {})
        metadata = acquired_data.get("metadata", {})
        
        # Simple normalization - in production, implement proper normalization
        normalized = {
            "content": data,
            "metadata": metadata,
            "normalized_at": datetime.utcnow().isoformat(),
            "hash": hashlib.sha256(
                json.dumps(data, sort_keys=True).encode()
            ).hexdigest()
        }
        
        return normalized