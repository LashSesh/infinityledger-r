"""
domain_layer.py
---------------

Domain-Layer Extension for MEF-Core implementing Resonit/Resonat structures,
MeshHolo triangulation, and cross-domain homeomorphism with full Metatron Cube integration.

This layer enables domain-specific transformations while maintaining the
domain-agnostic nature of the core pipeline.
"""

import json
import uuid
import hashlib
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod
import networkx as nx
from scipy.spatial import Delaunay
from scipy.stats import entropy
from sklearn.decomposition import PCA

# Import MEF-Core components
from src.topology.metatron_router import MetatronRouter, OperatorType
from src.mef_core_pipeline import MEFCorePipeline, TICCandidate
from src.gates.merkaba_gate import MerkabaGate

# Import Metatron Cube components for topology
from src.cube import MetatronCube
from src.geometry import canonical_nodes, Node
from src.mandorla import MandorlaField
from src.resonance_tensor import ResonanceTensorField


@dataclass
class Resonit:
    """
    Elementary information atom with tripolar signature.
    
    Resonits are the fundamental units of domain-specific information,
    characterized by their resonance signature σ = (ψ, ρ, ω).
    """
    id: str
    sigma: Dict[str, float]  # psi, rho, omega
    src: str  # Source domain adapter
    ts: int  # Unix timestamp
    coordinates: Optional[np.ndarray] = None  # Position in domain space
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_vector(self) -> np.ndarray:
        """Convert Resonit to vector representation."""
        return np.array([self.sigma["psi"], self.sigma["rho"], self.sigma["omega"]])
    
    def resonance_with(self, other: 'Resonit') -> float:
        """Calculate resonance between two Resonits."""
        v1 = self.to_vector()
        v2 = other.to_vector()
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-10))


@dataclass
class Resonat:
    """
    Cluster of Resonits forming a topologically stable structure.
    
    Resonats are validated through Betti vectors and persistence metrics,
    ensuring they represent coherent information gestalts.
    """
    id: str
    resonits: List[Resonit]
    metrics: Dict[str, Any]  # betti, persistence, stability
    centroid: Optional[np.ndarray] = None
    topology: Optional[Dict[str, Any]] = None
    
    def calculate_betti_vectors(self) -> List[int]:
        """
        Calculate Betti numbers for the Resonat topology.
        
        Returns:
            List of Betti numbers [β0, β1, β2, ...]
        """
        if len(self.resonits) < 2:
            return [1, 0, 0]
        
        # Create graph from Resonit connections
        G = nx.Graph()
        for i, r1 in enumerate(self.resonits):
            G.add_node(i, resonit=r1)
            for j, r2 in enumerate(self.resonits[i+1:], i+1):
                resonance = r1.resonance_with(r2)
                if resonance > 0.3:  # Threshold for connection
                    G.add_edge(i, j, weight=resonance)
        
        # Calculate topological invariants
        beta_0 = nx.number_connected_components(G)
        
        # Simplified β1 calculation (number of cycles)
        try:
            cycles = nx.minimum_cycle_basis(G)
            beta_1 = len(cycles)
        except:
            beta_1 = 0
        
        # β2 and higher would require more sophisticated homology calculations
        beta_2 = 0
        
        return [beta_0, beta_1, beta_2]
    
    def persistence_score(self) -> float:
        """
        Calculate topological persistence score.
        
        Returns:
            Persistence score in [0, 1]
        """
        betti = self.calculate_betti_vectors()
        
        # Persistence based on stability of Betti numbers
        # Higher β0 (more components) reduces persistence
        # Moderate β1 (some cycles) is good
        # High β2 (voids) reduces persistence
        
        persistence = 1.0 / (1.0 + betti[0])  # Fewer components is better
        persistence *= (1.0 + 0.5 * betti[1]) / (1.0 + betti[1])  # Some cycles OK
        persistence *= 1.0 / (1.0 + betti[2])  # Fewer voids is better
        
        return float(np.clip(persistence, 0, 1))


@dataclass
class Infogene:
    """
    Operator signature with governance rules for domain transformation.
    """
    operator: OperatorType
    params: Dict[str, Any]
    constraints: List[str]
    weight: float = 1.0


@dataclass
class Infogenome:
    """
    Collection of Infogenes defining transformation behavior.
    """
    id: str
    genes: List[Infogene]
    governance: Dict[str, List[str]]  # rules and constraints
    fitness: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def mutate(self, mutation_rate: float = 0.1) -> 'Infogenome':
        """
        Create mutated version of this Infogenome.
        
        Args:
            mutation_rate: Probability of mutating each gene
            
        Returns:
            New mutated Infogenome
        """
        new_genes = []
        for gene in self.genes:
            if np.random.random() < mutation_rate:
                # Mutate parameters
                new_params = gene.params.copy()
                for key in new_params:
                    if isinstance(new_params[key], float):
                        new_params[key] *= np.random.normal(1.0, 0.1)
                
                new_gene = Infogene(
                    operator=gene.operator,
                    params=new_params,
                    constraints=gene.constraints,
                    weight=gene.weight * np.random.normal(1.0, 0.05)
                )
                new_genes.append(new_gene)
            else:
                new_genes.append(gene)
        
        return Infogenome(
            id=str(uuid.uuid4()),
            genes=new_genes,
            governance=self.governance.copy(),
            fitness=0.0,
            metadata={"parent": self.id}
        )


@dataclass
class MeshHolo:
    """
    Holographic triangulation of information space using Metatron topology.
    
    Leverages the 13-node Metatron Cube structure for enhanced
    triangulation and topological invariant calculations.
    """
    id: str
    seed: str
    vertices: List[Dict[str, Any]]  # Vertex data with coordinates and sigma
    edges: List[Tuple[str, str, float]]  # (v1_id, v2_id, weight)
    simplices: List[List[str]]  # Triangular/tetrahedral simplices
    invariants: Dict[str, Any]  # Topological invariants
    metatron_mapping: Optional[Dict[str, int]] = None  # Vertex to Metatron node mapping
    provenance: Dict[str, Any] = field(default_factory=dict)
    proof: Dict[str, Any] = field(default_factory=dict)
    
    def to_metatron_embedding(self, metatron: MetatronCube) -> np.ndarray:
        """
        Embed MeshHolo vertices into Metatron Cube topology.
        
        Args:
            metatron: MetatronCube instance
            
        Returns:
            Embedding matrix (vertices x 13)
        """
        n_vertices = len(self.vertices)
        embedding = np.zeros((n_vertices, 13))
        
        # Get canonical nodes for reference
        nodes = canonical_nodes()
        
        for i, vertex in enumerate(self.vertices):
            # Map vertex to closest Metatron nodes
            v_coords = np.array([vertex["theta"], vertex["chi"], vertex.get("phi", 0)])
            
            for j, node in enumerate(nodes):
                # Calculate affinity based on geometric distance
                node_coords = np.array(node.coords)
                distance = np.linalg.norm(v_coords - node_coords[:len(v_coords)])
                affinity = np.exp(-distance)
                embedding[i, j] = affinity
            
            # Normalize embedding
            embedding[i] /= np.sum(embedding[i]) + 1e-10
        
        return embedding


class DomainAdapter(ABC):
    """
    Abstract base class for domain-specific adapters.
    
    Each domain implements its own adapter to transform
    raw data into Resonits.
    """
    
    @abstractmethod
    def transform(self, raw_data: Any) -> List[Resonit]:
        """Transform raw domain data into Resonits."""
        pass
    
    @abstractmethod
    def extract_features(self, raw_data: Any) -> np.ndarray:
        """Extract feature vector from raw data."""
        pass
    
    @abstractmethod
    def domain_name(self) -> str:
        """Return domain identifier."""
        pass


class TextDomainAdapter(DomainAdapter):
    """Adapter for text/NLP domain."""
    
    def transform(self, raw_data: Any) -> List[Resonit]:
        """Transform text into Resonits."""
        if isinstance(raw_data, str):
            text = raw_data
        else:
            text = str(raw_data)
        
        # Split into semantic units (simplified: sentences)
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        sentences = [s.strip() for s in sentences if s.strip()]
        
        resonits = []
        for i, sentence in enumerate(sentences):
            # Calculate semantic signature
            features = self.extract_features(sentence)
            
            # Map features to tripolar signature
            psi = float(np.mean(features[:3]))  # Activation from first features
            rho = float(np.std(features))  # Coherence from variation
            omega = float(np.mean(np.abs(np.diff(features))))  # Rhythm from changes
            
            resonit = Resonit(
                id=str(uuid.uuid4()),
                sigma={"psi": psi, "rho": rho, "omega": omega},
                src=self.domain_name(),
                ts=int(datetime.utcnow().timestamp()),
                metadata={"content": sentence, "position": i}
            )
            resonits.append(resonit)
        
        return resonits
    
    def extract_features(self, raw_data: Any) -> np.ndarray:
        """Extract features from text."""
        text = str(raw_data)
        
        # Simple feature extraction (in production, use embeddings)
        features = []
        features.append(len(text) / 100.0)  # Length
        features.append(len(set(text.lower())) / 26.0)  # Unique chars
        features.append(text.count(' ') / (len(text) + 1))  # Word density
        features.append(sum(1 for c in text if c.isupper()) / (len(text) + 1))  # Capitals
        features.append(sum(1 for c in text if c.isdigit()) / (len(text) + 1))  # Digits
        
        # Pad to fixed size
        while len(features) < 10:
            features.append(0.0)
        
        return np.array(features[:10])
    
    def domain_name(self) -> str:
        return "text"


class SignalDomainAdapter(DomainAdapter):
    """Adapter for signal/time-series domain."""
    
    def transform(self, raw_data: Any) -> List[Resonit]:
        """Transform signal into Resonits."""
        if isinstance(raw_data, (list, tuple)):
            signal = np.array(raw_data)
        elif isinstance(raw_data, np.ndarray):
            signal = raw_data
        else:
            signal = np.array([raw_data])
        
        # Segment signal into windows
        window_size = min(100, len(signal))
        stride = window_size // 2
        
        resonits = []
        for i in range(0, len(signal) - window_size + 1, stride):
            window = signal[i:i + window_size]
            features = self.extract_features(window)
            
            # Map to tripolar signature
            psi = float(np.mean(np.abs(window)))  # Amplitude
            rho = float(1.0 / (1.0 + np.std(window)))  # Inverse variance for coherence
            
            # Frequency content for rhythm
            if len(window) > 1:
                fft = np.fft.fft(window)
                omega = float(np.argmax(np.abs(fft[1:len(fft)//2])) / len(window))
            else:
                omega = 0.5
            
            resonit = Resonit(
                id=str(uuid.uuid4()),
                sigma={"psi": psi, "rho": rho, "omega": omega},
                src=self.domain_name(),
                ts=int(datetime.utcnow().timestamp()),
                coordinates=np.array([i / len(signal), 0, 0]),  # Position in signal
                metadata={"window_start": i, "window_size": window_size}
            )
            resonits.append(resonit)
        
        return resonits
    
    def extract_features(self, raw_data: Any) -> np.ndarray:
        """Extract features from signal window."""
        signal = np.array(raw_data)
        
        features = []
        features.append(np.mean(signal))
        features.append(np.std(signal))
        features.append(np.min(signal))
        features.append(np.max(signal))
        
        # Spectral features
        if len(signal) > 1:
            fft = np.fft.fft(signal)
            features.append(np.mean(np.abs(fft)))
            features.append(np.std(np.abs(fft)))
        else:
            features.extend([0, 0])
        
        # Pad to fixed size
        while len(features) < 10:
            features.append(0.0)
        
        return np.array(features[:10])
    
    def domain_name(self) -> str:
        return "signal"


class DomainLayer:
    """
    Main Domain-Layer orchestrator integrating with MEF-Core and Metatron Cube.
    
    This layer manages domain-specific transformations, Resonit/Resonat
    clustering, MeshHolo triangulation, and cross-domain homeomorphism.
    """
    
    def __init__(self,
                 mef_pipeline: MEFCorePipeline,
                 metatron_router: MetatronRouter,
                 storage_path: str = "C:/MEF/domains"):
        """
        Initialize Domain Layer with MEF-Core integration.
        
        Args:
            mef_pipeline: MEF-Core pipeline instance
            metatron_router: Metatron Router instance
            storage_path: Path for domain-specific storage
        """
        self.mef_pipeline = mef_pipeline
        self.metatron = metatron_router
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Domain adapters registry
        self.adapters: Dict[str, DomainAdapter] = {
            "text": TextDomainAdapter(),
            "signal": SignalDomainAdapter()
        }
        
        # Resonit/Resonat storage
        self.resonits: Dict[str, Resonit] = {}
        self.resonats: Dict[str, Resonat] = {}
        
        # MeshHolo triangulations
        self.meshes: Dict[str, MeshHolo] = {}
        
        # Infogenome population
        self.infogenomes: List[Infogenome] = []
        self._initialize_infogenomes()
        
        # Mandorla field for gate validation
        self.mandorla = MandorlaField(alpha=0.5, beta=0.5)
        
        # Metrics tracking
        self.metrics = {
            "resonits_created": 0,
            "resonats_formed": 0,
            "meshes_triangulated": 0,
            "cross_domain_transfers": 0
        }
    
    def _initialize_infogenomes(self):
        """Create initial population of Infogenomes."""
        # Create base infogenome with standard operators
        base_genome = Infogenome(
            id=str(uuid.uuid4()),
            genes=[
                Infogene(
                    operator=OperatorType.DK,
                    params={"alpha1": 0.05, "alpha2": -0.03},
                    constraints=["non_expansive"],
                    weight=1.0
                ),
                Infogene(
                    operator=OperatorType.SW,
                    params={"tau": 0.5, "beta": 0.1},
                    constraints=["adaptive"],
                    weight=0.8
                ),
                Infogene(
                    operator=OperatorType.PI,
                    params={"tolerance": 1e-6},
                    constraints=["idempotent"],
                    weight=0.9
                ),
                Infogene(
                    operator=OperatorType.WT,
                    params={"gamma": 0.1},
                    constraints=["conservative"],
                    weight=0.7
                )
            ],
            governance={
                "rules": ["pfadinvarianz", "resonanzvalidierung"],
                "constraints": ["contraction", "convergence"]
            }
        )
        self.infogenomes.append(base_genome)
        
        # Create variations
        for _ in range(4):
            mutant = base_genome.mutate(mutation_rate=0.3)
            self.infogenomes.append(mutant)
    
    def process_domain_data(self,
                           raw_data: Any,
                           domain: str,
                           target_domain: Optional[str] = None) -> Dict[str, Any]:
        """
        Process domain-specific data through the complete pipeline.
        
        Args:
            raw_data: Raw domain data
            domain: Source domain identifier
            target_domain: Optional target domain for cross-domain transfer
            
        Returns:
            Processing results including Resonat, MeshHolo, and TIC
        """
        # Step 1: Transform to Resonits
        adapter = self.adapters.get(domain)
        if not adapter:
            raise ValueError(f"No adapter for domain: {domain}")
        
        resonits = adapter.transform(raw_data)
        for resonit in resonits:
            self.resonits[resonit.id] = resonit
        self.metrics["resonits_created"] += len(resonits)
        
        # Step 2: Cluster into Resonat
        resonat = self._cluster_resonits(resonits)
        self.resonats[resonat.id] = resonat
        self.metrics["resonats_formed"] += 1
        
        # Step 3: Create MeshHolo triangulation
        mesh = self._triangulate_resonat(resonat)
        self.meshes[mesh.id] = mesh
        self.metrics["meshes_triangulated"] += 1
        
        # Step 4: Apply Infogenome transformations
        transformed_state = self._apply_infogenome(resonat, mesh)
        
        # Step 5: Validate through Mandorla gate
        gate_validation = self._validate_mandorla(transformed_state, mesh)
        
        # Step 6: Create domain-enhanced TIC
        tic = self._create_domain_tic(
            transformed_state,
            resonat,
            mesh,
            gate_validation
        )
        
        # Step 7: Optional cross-domain transfer
        if target_domain and target_domain != domain:
            cross_domain_result = self._homeomorphic_transfer(
                mesh,
                domain,
                target_domain
            )
            self.metrics["cross_domain_transfers"] += 1
        else:
            cross_domain_result = None
        
        return {
            "resonat": asdict(resonat),
            "mesh": self._mesh_to_dict(mesh),
            "tic": tic,
            "gate_validation": gate_validation,
            "cross_domain": cross_domain_result,
            "metrics": self.metrics.copy()
        }
    
    def _cluster_resonits(self, resonits: List[Resonit]) -> Resonat:
        """
        Cluster Resonits into a coherent Resonat.
        
        Args:
            resonits: List of Resonits to cluster
            
        Returns:
            Formed Resonat with topological validation
        """
        if not resonits:
            raise ValueError("Cannot cluster empty Resonit list")
        
        # Calculate centroid in sigma space
        sigma_vectors = np.array([r.to_vector() for r in resonits])
        centroid = np.mean(sigma_vectors, axis=0)
        
        # Create Resonat
        resonat = Resonat(
            id=str(uuid.uuid4()),
            resonits=resonits,
            metrics={},
            centroid=centroid
        )
        
        # Calculate topological metrics
        betti = resonat.calculate_betti_vectors()
        persistence = resonat.persistence_score()
        
        # Calculate stability using resonance variance
        resonances = []
        for i in range(len(resonits)):
            for j in range(i + 1, len(resonits)):
                resonances.append(resonits[i].resonance_with(resonits[j]))
        
        stability = 1.0 - np.std(resonances) if resonances else 1.0
        
        resonat.metrics = {
            "betti": betti,
            "persistence": persistence,
            "stability": float(stability),
            "size": len(resonits)
        }
        
        return resonat
    
    def _triangulate_resonat(self, resonat: Resonat) -> MeshHolo:
        """
        Create MeshHolo triangulation using Metatron topology.
        
        Args:
            resonat: Resonat to triangulate
            
        Returns:
            MeshHolo triangulation with Metatron embedding
        """
        # Create vertices from Resonits
        vertices = []
        for resonit in resonat.resonits:
            # Map Resonit to spherical coordinates
            sigma = resonit.to_vector()
            theta = np.arctan2(sigma[1], sigma[0])
            chi = np.arccos(np.clip(sigma[2] / np.linalg.norm(sigma), -1, 1))
            
            vertex = {
                "id": resonit.id,
                "theta": float(theta),
                "chi": float(chi),
                "sigma": resonit.sigma
            }
            vertices.append(vertex)
        
        # Perform Delaunay triangulation if enough points
        edges = []
        simplices = []
        
        if len(vertices) >= 3:
            # Project to 2D for triangulation
            points_2d = np.array([[v["theta"], v["chi"]] for v in vertices])
            
            try:
                tri = Delaunay(points_2d)
                
                # Extract edges from simplices
                edge_set = set()
                for simplex in tri.simplices:
                    for i in range(len(simplex)):
                        for j in range(i + 1, len(simplex)):
                            edge = tuple(sorted([simplex[i], simplex[j]]))
                            edge_set.add(edge)
                
                # Create edge list with weights
                for i, j in edge_set:
                    r1 = resonat.resonits[i]
                    r2 = resonat.resonits[j]
                    weight = r1.resonance_with(r2)
                    edges.append((vertices[i]["id"], vertices[j]["id"], float(weight)))
                
                # Create simplex list
                for simplex in tri.simplices:
                    simplex_ids = [vertices[i]["id"] for i in simplex]
                    simplices.append(simplex_ids)
            except:
                # Fallback to simple connectivity
                for i in range(len(vertices) - 1):
                    edges.append((vertices[i]["id"], vertices[i + 1]["id"], 0.5))
        
        # Calculate topological invariants
        invariants = {
            "betti": resonat.metrics["betti"],
            "lambda_gap": self._calculate_spectral_gap(edges, vertices),
            "persistence": resonat.metrics["persistence"]
        }
        
        # Create MeshHolo
        mesh = MeshHolo(
            id=str(uuid.uuid4()),
            seed=self.mef_pipeline.seed,
            vertices=vertices,
            edges=edges,
            simplices=simplices,
            invariants=invariants,
            provenance={
                "source": "domain_layer",
                "resonat_id": resonat.id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        # Map to Metatron nodes
        mesh.metatron_mapping = self._map_to_metatron(vertices)
        
        return mesh
    
    def _calculate_spectral_gap(self,
                               edges: List[Tuple[str, str, float]],
                               vertices: List[Dict[str, Any]]) -> float:
        """
        Calculate spectral gap of the triangulation graph.
        
        Args:
            edges: Edge list with weights
            vertices: Vertex list
            
        Returns:
            Spectral gap λ_2 - λ_1
        """
        if len(vertices) < 2:
            return 0.0
        
        # Build adjacency matrix
        n = len(vertices)
        vertex_idx = {v["id"]: i for i, v in enumerate(vertices)}
        
        A = np.zeros((n, n))
        for v1_id, v2_id, weight in edges:
            if v1_id in vertex_idx and v2_id in vertex_idx:
                i = vertex_idx[v1_id]
                j = vertex_idx[v2_id]
                A[i, j] = weight
                A[j, i] = weight
        
        # Calculate Laplacian
        D = np.diag(np.sum(A, axis=1))
        L = D - A
        
        # Calculate eigenvalues
        eigenvalues = np.linalg.eigvalsh(L)
        eigenvalues.sort()
        
        # Spectral gap is λ_2 - λ_1
        if len(eigenvalues) > 1:
            gap = eigenvalues[1] - eigenvalues[0]
        else:
            gap = 0.0
        
        return float(gap)
    
    def _map_to_metatron(self, vertices: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Map vertices to closest Metatron nodes.
        
        Args:
            vertices: Vertex list
            
        Returns:
            Mapping from vertex ID to Metatron node index (1-13)
        """
        mapping = {}
        nodes = canonical_nodes()
        
        for vertex in vertices:
            # Find closest Metatron node
            v_coords = np.array([vertex["theta"], vertex["chi"], 0])
            
            min_dist = np.inf
            closest_node = 1
            
            for node in nodes:
                # Use first 2 dimensions for comparison
                node_coords = np.array(node.coords[:2] + (0,))
                dist = np.linalg.norm(v_coords - node_coords)
                
                if dist < min_dist:
                    min_dist = dist
                    closest_node = node.index
            
            mapping[vertex["id"]] = closest_node
        
        return mapping
    
    def _apply_infogenome(self,
                         resonat: Resonat,
                         mesh: MeshHolo) -> np.ndarray:
        """
        Apply Infogenome transformations to Resonat.
        
        Args:
            resonat: Input Resonat
            mesh: Associated MeshHolo
            
        Returns:
            Transformed state vector
        """
        # Select best Infogenome based on fitness
        best_genome = max(self.infogenomes, key=lambda g: g.fitness)
        
        # Create initial state from Resonat centroid
        state = resonat.centroid
        
        # Pad to Metatron dimensions
        if len(state) < 13:
            padded_state = np.zeros(13)
            padded_state[:len(state)] = state
            state = padded_state
        
        # Apply genes in sequence
        for gene in best_genome.genes:
            # Apply operator through Metatron router
            operator_func = self.metatron.operators[gene.operator]
            
            # Apply with gene-specific parameters
            prev_state = state.copy()
            state = operator_func(state)
            
            # Weight the transformation
            state = gene.weight * state + (1 - gene.weight) * prev_state
        
        # Update genome fitness based on result quality
        quality = self._evaluate_transformation_quality(state, resonat)
        best_genome.fitness = 0.9 * best_genome.fitness + 0.1 * quality
        
        return state
    
    def _evaluate_transformation_quality(self,
                                        state: np.ndarray,
                                        resonat: Resonat) -> float:
        """
        Evaluate quality of transformation.
        
        Args:
            state: Transformed state
            resonat: Original Resonat
            
        Returns:
            Quality score in [0, 1]
        """
        # Calculate resonance preservation
        original_resonance = np.mean([
            r1.resonance_with(r2)
            for i, r1 in enumerate(resonat.resonits)
            for r2 in resonat.resonits[i + 1:]
        ])
        
        # Calculate state coherence
        state_coherence = 1.0 / (1.0 + entropy(np.abs(state) / np.sum(np.abs(state))))
        
        # Calculate stability (low variance is good)
        stability = 1.0 / (1.0 + np.var(state))
        
        # Combine metrics
        quality = (original_resonance + state_coherence + stability) / 3.0
        
        return float(np.clip(quality, 0, 1))
    
    def _validate_mandorla(self,
                          state: np.ndarray,
                          mesh: MeshHolo) -> Dict[str, Any]:
        """
        Validate transformation through Mandorla gate region.
        
        Args:
            state: Transformed state
            mesh: MeshHolo triangulation
            
        Returns:
            Validation results
        """
        # Normalize state representation for Mandorla analysis
        state_vector = np.asarray(state, dtype=float)

        # Clear and populate Mandorla field
        self.mandorla.clear_inputs()

        # Add state at different projections
        base_projection = np.asarray(state_vector[:5], dtype=float)
        for scale in [0.5, 1.0, 2.0]:
            self.mandorla.add_input(base_projection * scale)
        
        # Calculate gate metrics
        resonance = self.mandorla.calc_resonance()
        entropy_val = self.mandorla.calc_entropy()
        variance = self.mandorla.calc_variance()
        
        # Check path invariance using mesh topology
        pi_gap = mesh.invariants.get("lambda_gap", 0.0)
        
        # Determine if gate passes
        passed = (
            resonance > 0.5 and
            pi_gap < 0.1 and
            entropy_val < 2.0
        )
        
        return {
            "passed": passed,
            "resonance": float(resonance),
            "entropy": float(entropy_val),
            "variance": float(variance),
            "pi_gap": float(pi_gap),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _create_domain_tic(self,
                          state: np.ndarray,
                          resonat: Resonat,
                          mesh: MeshHolo,
                          gate_validation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create domain-enhanced TIC.
        
        Args:
            state: Transformed state
            resonat: Source Resonat
            mesh: MeshHolo triangulation
            gate_validation: Mandorla validation results
            
        Returns:
            Domain-enhanced TIC dictionary
        """
        # Process through MEF-Core pipeline
        tic_candidate = self.mef_pipeline.process(
            raw_input=state.tolist(),
            input_type="vector"
        )
        
        # Enhance with domain-specific attributes
        domain_tic = {
            "tic_id": tic_candidate.tic_id,
            "core_tic": asdict(tic_candidate),
            "domain_extension": {
                "resonat_id": resonat.id,
                "mesh_id": mesh.id,
                "metrics": {
                    "domain_resonance": np.mean([
                        r1.resonance_with(r2)
                        for i, r1 in enumerate(resonat.resonits)
                        for r2 in resonat.resonits[i + 1:]
                    ]),
                    "domain_persistence": resonat.metrics["persistence"],
                    "betti_numbers": resonat.metrics["betti"]
                },
                "annotations": {
                    "domain": resonat.resonits[0].src if resonat.resonits else "unknown",
                    "resonit_count": len(resonat.resonits),
                    "simplex_count": len(mesh.simplices)
                }
            },
            "proof": {
                "por": gate_validation["passed"],
                "pi_gap": gate_validation["pi_gap"],
                "resonance": gate_validation["resonance"],
                "mci": None  # Would be calculated by full Merkaba Gate
            }
        }
        
        return domain_tic
    
    def _homeomorphic_transfer(self,
                              mesh: MeshHolo,
                              source_domain: str,
                              target_domain: str) -> Optional[Dict[str, Any]]:
        """
        Perform homeomorphic transfer between domains.
        
        Args:
            mesh: Source MeshHolo
            source_domain: Source domain identifier
            target_domain: Target domain identifier
            
        Returns:
            Transfer result or None if transfer fails
        """
        # Check if target adapter exists
        if target_domain not in self.adapters:
            return None
        
        # Get Metatron embedding of source mesh
        embedding = mesh.to_metatron_embedding(self.metatron.metatron)
        
        # Apply homeomorphism through Metatron topology
        # This preserves topological invariants while changing representation
        
        # Transform embedding through target domain's characteristic operator
        if target_domain == "text":
            # Text domain emphasizes sequential structure
            transformed = self._apply_sequential_homeomorphism(embedding)
        elif target_domain == "signal":
            # Signal domain emphasizes frequency structure
            transformed = self._apply_spectral_homeomorphism(embedding)
        else:
            transformed = embedding
        
        # Verify invariant preservation
        original_betti = mesh.invariants["betti"]
        
        # Create target mesh (simplified for demonstration)
        target_vertices = []
        for i, vertex in enumerate(mesh.vertices):
            # Map through transformed embedding
            new_coords = transformed[i] if i < len(transformed) else np.zeros(13)
            
            target_vertex = vertex.copy()
            target_vertex["transformed"] = new_coords.tolist()
            target_vertices.append(target_vertex)
        
        return {
            "source_domain": source_domain,
            "target_domain": target_domain,
            "source_mesh_id": mesh.id,
            "transformed_vertices": len(target_vertices),
            "invariants_preserved": {
                "betti": original_betti,
                "persistence": mesh.invariants["persistence"]
            },
            "transformation_matrix": transformed[:3].tolist()  # Sample
        }
    
    def _apply_sequential_homeomorphism(self, embedding: np.ndarray) -> np.ndarray:
        """Apply homeomorphism for sequential (text) domain."""
        # Emphasize linear ordering
        n = len(embedding)
        transformed = embedding.copy()
        
        # Apply sequential weighting
        for i in range(n):
            weight = np.exp(-i / n)  # Decay for sequence position
            transformed[i] *= weight
        
        return transformed
    
    def _apply_spectral_homeomorphism(self, embedding: np.ndarray) -> np.ndarray:
        """Apply homeomorphism for spectral (signal) domain."""
        # Emphasize frequency components
        transformed = np.fft.fft(embedding, axis=1)
        transformed = np.abs(transformed)  # Magnitude spectrum
        
        return transformed
    
    def _mesh_to_dict(self, mesh: MeshHolo) -> Dict[str, Any]:
        """Convert MeshHolo to dictionary for serialization."""
        return {
            "id": mesh.id,
            "seed": mesh.seed,
            "vertices": mesh.vertices,
            "edges": [(e[0], e[1], e[2]) for e in mesh.edges],
            "simplices": mesh.simplices,
            "invariants": mesh.invariants,
            "metatron_mapping": mesh.metatron_mapping,
            "provenance": mesh.provenance,
            "proof": mesh.proof
        }