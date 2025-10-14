"""
api_domain_layer.py
-------------------

REST API endpoints for Domain Layer Extension integration with MEF-Core.
Provides domain-specific processing, Resonit/Resonat management, MeshHolo
triangulation, and cross-domain homeomorphic transfer capabilities.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import json
import io
import numpy as np
from pathlib import Path

# Import Domain Layer components
from src.domains.domain_layer import (
    DomainLayer,
    Resonit,
    Resonat,
    MeshHolo,
    Infogenome,
    TextDomainAdapter,
    SignalDomainAdapter
)

# Import MEF-Core and Metatron components
from src.mef_core_pipeline import MEFCorePipeline
from src.topology.metatron_router import MetatronRouter


# ========================
# Pydantic Models
# ========================

class DomainProcessRequest(BaseModel):
    """Request model for domain data processing."""
    raw_data: Union[str, List[float], Dict[str, Any]] = Field(
        ..., 
        description="Raw domain-specific data"
    )
    source_domain: str = Field(
        ...,
        description="Source domain (text, signal, graph, etc.)"
    )
    target_domain: Optional[str] = Field(
        default=None,
        description="Target domain for homeomorphic transfer"
    )
    use_cached_infogenome: bool = Field(
        default=True,
        description="Use best-performing cached Infogenome"
    )


class ResonitCreateRequest(BaseModel):
    """Request model for manual Resonit creation."""
    psi: float = Field(..., ge=0, le=1, description="Activation level")
    rho: float = Field(..., ge=0, le=1, description="Coherence")
    omega: float = Field(..., ge=0, le=1, description="Rhythm")
    metadata: Optional[Dict[str, Any]] = None


class ResonatClusterRequest(BaseModel):
    """Request model for clustering Resonits into Resonats."""
    resonit_ids: List[str] = Field(
        ...,
        min_items=2,
        description="List of Resonit IDs to cluster"
    )
    min_persistence: float = Field(
        default=0.3,
        ge=0,
        le=1,
        description="Minimum persistence score required"
    )


class MeshTriangulationRequest(BaseModel):
    """Request model for MeshHolo triangulation."""
    resonat_id: str = Field(..., description="Resonat ID to triangulate")
    use_metatron_embedding: bool = Field(
        default=True,
        description="Embed into Metatron topology"
    )


class CrossDomainTransferRequest(BaseModel):
    """Request model for cross-domain homeomorphic transfer."""
    mesh_id: str = Field(..., description="Source MeshHolo ID")
    source_domain: str = Field(..., description="Source domain")
    target_domain: str = Field(..., description="Target domain")
    preserve_invariants: bool = Field(
        default=True,
        description="Ensure topological invariants are preserved"
    )


class InfgenomeEvolutionRequest(BaseModel):
    """Request model for Infogenome evolution."""
    generations: int = Field(default=10, ge=1, le=100)
    population_size: int = Field(default=20, ge=5, le=100)
    mutation_rate: float = Field(default=0.1, ge=0, le=1)
    selection_pressure: float = Field(default=0.7, ge=0, le=1)


# ========================
# API Extension Functions
# ========================

def create_domain_api(app: FastAPI):
    """
    Create comprehensive Domain Layer API endpoints.
    
    Args:
        app: FastAPI application instance
    """
    
    # Initialize MEF-Core with Metatron
    mef_pipeline = MEFCorePipeline(
        seed="MEF_DOMAIN_API",
        storage_path="C:/MEF/store",
        ledger_path="C:/MEF/ledger",
        metatron_cache=True
    )
    
    metatron_router = mef_pipeline.metatron_router
    
    # Initialize Domain Layer
    domain_layer = DomainLayer(
        mef_pipeline=mef_pipeline,
        metatron_router=metatron_router,
        storage_path="C:/MEF/domains"
    )
    
    # ========================
    # Domain Processing Endpoints
    # ========================
    
    @app.post("/domain/process")
    async def process_domain_data(
        request: DomainProcessRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Process domain-specific data through complete Domain Layer pipeline.
        
        Flow: Raw Data → Resonits → Resonat → MeshHolo → Infogenome Transform → 
        Mandorla Validation → Domain TIC → Optional Cross-Domain Transfer
        """
        try:
            result = domain_layer.process_domain_data(
                raw_data=request.raw_data,
                domain=request.source_domain,
                target_domain=request.target_domain
            )
            
            # Schedule background persistence
            background_tasks.add_task(
                persist_domain_artifacts,
                domain_layer,
                result
            )
            
            return {
                "status": "processed",
                "resonat": {
                    "id": result["resonat"]["id"],
                    "resonit_count": len(result["resonat"]["resonits"]),
                    "metrics": result["resonat"]["metrics"]
                },
                "mesh": {
                    "id": result["mesh"]["id"],
                    "vertex_count": len(result["mesh"]["vertices"]),
                    "simplex_count": len(result["mesh"]["simplices"]),
                    "invariants": result["mesh"]["invariants"]
                },
                "tic": {
                    "id": result["tic"]["tic_id"],
                    "domain": result["tic"]["domain_extension"]["annotations"]["domain"],
                    "proof": result["tic"]["proof"]
                },
                "cross_domain": result["cross_domain"],
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Domain processing failed: {str(e)}"
            )
    
    @app.post("/domain/process/file")
    async def process_domain_file(
        file: UploadFile = File(...),
        source_domain: str = Query(...),
        target_domain: Optional[str] = Query(None)
    ):
        """
        Process uploaded file through Domain Layer.
        
        Automatically detects content type and processes accordingly.
        """
        try:
            content = await file.read()
            
            # Detect content type
            if file.content_type and "text" in file.content_type:
                raw_data = content.decode('utf-8')
                domain = "text"
            elif file.content_type and "json" in file.content_type:
                raw_data = json.loads(content)
                domain = source_domain or "json"
            else:
                # Assume binary/signal data
                raw_data = list(np.frombuffer(content, dtype=np.uint8))
                domain = "signal"
            
            # Override with specified domain if provided
            if source_domain:
                domain = source_domain
            
            # Process through domain layer
            result = domain_layer.process_domain_data(
                raw_data=raw_data,
                domain=domain,
                target_domain=target_domain
            )
            
            return {
                "filename": file.filename,
                "content_type": file.content_type,
                "detected_domain": domain,
                "processing_result": {
                    "resonat_id": result["resonat"]["id"],
                    "mesh_id": result["mesh"]["id"],
                    "tic_id": result["tic"]["tic_id"]
                }
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"File processing failed: {str(e)}"
            )
    
    # ========================
    # Resonit/Resonat Management
    # ========================
    
    @app.post("/domain/resonit/create")
    async def create_resonit(request: ResonitCreateRequest):
        """Create a new Resonit manually."""
        resonit = Resonit(
            id=str(uuid.uuid4()),
            sigma={
                "psi": request.psi,
                "rho": request.rho,
                "omega": request.omega
            },
            src="manual",
            ts=int(datetime.utcnow().timestamp()),
            metadata=request.metadata or {}
        )
        
        domain_layer.resonits[resonit.id] = resonit
        
        return {
            "resonit_id": resonit.id,
            "sigma": resonit.sigma,
            "created": True
        }
    
    @app.get("/domain/resonit/{resonit_id}")
    async def get_resonit(resonit_id: str):
        """Retrieve specific Resonit by ID."""
        if resonit_id not in domain_layer.resonits:
            raise HTTPException(status_code=404, detail="Resonit not found")
        
        resonit = domain_layer.resonits[resonit_id]
        return {
            "id": resonit.id,
            "sigma": resonit.sigma,
            "src": resonit.src,
            "ts": resonit.ts,
            "metadata": resonit.metadata
        }
    
    @app.post("/domain/resonat/cluster")
    async def cluster_resonits(request: ResonatClusterRequest):
        """Cluster specified Resonits into a Resonat."""
        # Gather Resonits
        resonits = []
        for rid in request.resonit_ids:
            if rid in domain_layer.resonits:
                resonits.append(domain_layer.resonits[rid])
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Resonit {rid} not found"
                )
        
        # Create Resonat
        resonat = domain_layer._cluster_resonits(resonits)
        
        # Check persistence requirement
        if resonat.metrics["persistence"] < request.min_persistence:
            return {
                "success": False,
                "reason": f"Persistence {resonat.metrics['persistence']:.3f} below minimum {request.min_persistence}",
                "metrics": resonat.metrics
            }
        
        # Store Resonat
        domain_layer.resonats[resonat.id] = resonat
        
        return {
            "success": True,
            "resonat_id": resonat.id,
            "metrics": resonat.metrics,
            "betti_vectors": resonat.calculate_betti_vectors()
        }
    
    @app.get("/domain/resonat/{resonat_id}")
    async def get_resonat(resonat_id: str):
        """Retrieve specific Resonat by ID."""
        if resonat_id not in domain_layer.resonats:
            raise HTTPException(status_code=404, detail="Resonat not found")
        
        resonat = domain_layer.resonats[resonat_id]
        return {
            "id": resonat.id,
            "resonit_count": len(resonat.resonits),
            "metrics": resonat.metrics,
            "centroid": resonat.centroid.tolist() if resonat.centroid is not None else None,
            "topology": resonat.topology
        }
    
    # ========================
    # MeshHolo Triangulation
    # ========================
    
    @app.post("/domain/mesh/triangulate")
    async def triangulate_resonat(request: MeshTriangulationRequest):
        """Create MeshHolo triangulation from Resonat."""
        if request.resonat_id not in domain_layer.resonats:
            raise HTTPException(status_code=404, detail="Resonat not found")
        
        resonat = domain_layer.resonats[request.resonat_id]
        mesh = domain_layer._triangulate_resonat(resonat)
        
        # Store mesh
        domain_layer.meshes[mesh.id] = mesh
        
        # Optional Metatron embedding
        embedding_info = None
        if request.use_metatron_embedding:
            embedding = mesh.to_metatron_embedding(domain_layer.metatron.metatron)
            embedding_info = {
                "shape": embedding.shape,
                "mean_affinity": float(np.mean(embedding)),
                "max_affinity_nodes": [
                    int(np.argmax(embedding[i])) + 1  # 1-based indexing
                    for i in range(min(3, len(embedding)))
                ]
            }
        
        return {
            "mesh_id": mesh.id,
            "vertex_count": len(mesh.vertices),
            "edge_count": len(mesh.edges),
            "simplex_count": len(mesh.simplices),
            "invariants": mesh.invariants,
            "metatron_embedding": embedding_info
        }
    
    @app.get("/domain/mesh/{mesh_id}")
    async def get_mesh(mesh_id: str, format: str = Query("json", regex="^(json|obj|ply)$")):
        """
        Retrieve MeshHolo triangulation.
        
        Formats: json (full data), obj (3D model), ply (point cloud)
        """
        if mesh_id not in domain_layer.meshes:
            raise HTTPException(status_code=404, detail="Mesh not found")
        
        mesh = domain_layer.meshes[mesh_id]
        
        if format == "json":
            return domain_layer._mesh_to_dict(mesh)
        
        elif format == "obj":
            # Export as Wavefront OBJ
            obj_content = export_mesh_as_obj(mesh)
            return StreamingResponse(
                io.BytesIO(obj_content.encode()),
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=mesh_{mesh_id[:8]}.obj"
                }
            )
        
        elif format == "ply":
            # Export as PLY point cloud
            ply_content = export_mesh_as_ply(mesh)
            return StreamingResponse(
                io.BytesIO(ply_content.encode()),
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=mesh_{mesh_id[:8]}.ply"
                }
            )
    
    # ========================
    # Cross-Domain Transfer
    # ========================
    
    @app.post("/domain/transfer/homeomorphic")
    async def perform_homeomorphic_transfer(request: CrossDomainTransferRequest):
        """
        Perform homeomorphic transfer between domains.
        
        Preserves topological invariants while changing representation.
        """
        if request.mesh_id not in domain_layer.meshes:
            raise HTTPException(status_code=404, detail="Mesh not found")
        
        mesh = domain_layer.meshes[request.mesh_id]
        
        # Perform transfer
        result = domain_layer._homeomorphic_transfer(
            mesh,
            request.source_domain,
            request.target_domain
        )
        
        if result is None:
            raise HTTPException(
                status_code=400,
                detail=f"Transfer from {request.source_domain} to {request.target_domain} not supported"
            )
        
        # Verify invariant preservation if requested
        if request.preserve_invariants:
            original_betti = mesh.invariants["betti"]
            if result["invariants_preserved"]["betti"] != original_betti:
                return {
                    "success": False,
                    "reason": "Topological invariants not preserved",
                    "original_betti": original_betti,
                    "result_betti": result["invariants_preserved"]["betti"]
                }
        
        return {
            "success": True,
            "transfer": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/domain/transfer/compatibility")
    async def check_domain_compatibility(
        source: str = Query(...),
        target: str = Query(...)
    ):
        """Check compatibility between two domains for transfer."""
        # Check if adapters exist
        source_exists = source in domain_layer.adapters
        target_exists = target in domain_layer.adapters
        
        if not source_exists or not target_exists:
            return {
                "compatible": False,
                "reason": "Missing adapter(s)",
                "source_adapter": source_exists,
                "target_adapter": target_exists
            }
        
        # Define compatibility matrix
        compatibility = {
            ("text", "signal"): {"compatible": True, "quality": 0.7},
            ("signal", "text"): {"compatible": True, "quality": 0.6},
            ("text", "text"): {"compatible": True, "quality": 1.0},
            ("signal", "signal"): {"compatible": True, "quality": 1.0}
        }
        
        key = (source, target)
        if key in compatibility:
            return compatibility[key]
        else:
            return {"compatible": False, "reason": "Unsupported transfer path"}
    
    # ========================
    # Infogenome Evolution
    # ========================
    
    @app.post("/domain/infogenome/evolve")
    async def evolve_infogenomes(request: InfgenomeEvolutionRequest):
        """
        Evolve Infogenome population through genetic algorithm.
        
        Improves transformation quality over generations.
        """
        initial_pop_size = len(domain_layer.infogenomes)
        
        for generation in range(request.generations):
            # Ensure population size
            while len(domain_layer.infogenomes) < request.population_size:
                # Create new random genome
                parent = np.random.choice(domain_layer.infogenomes)
                child = parent.mutate(request.mutation_rate)
                domain_layer.infogenomes.append(child)
            
            # Selection (keep top performers)
            domain_layer.infogenomes.sort(key=lambda g: g.fitness, reverse=True)
            survivors = int(len(domain_layer.infogenomes) * request.selection_pressure)
            domain_layer.infogenomes = domain_layer.infogenomes[:survivors]
            
            # Reproduce to fill population
            while len(domain_layer.infogenomes) < request.population_size:
                parent = np.random.choice(domain_layer.infogenomes[:survivors])
                child = parent.mutate(request.mutation_rate)
                domain_layer.infogenomes.append(child)
        
        # Get best genome stats
        best = max(domain_layer.infogenomes, key=lambda g: g.fitness)
        
        return {
            "generations_run": request.generations,
            "final_population": len(domain_layer.infogenomes),
            "best_genome": {
                "id": best.id,
                "fitness": best.fitness,
                "gene_count": len(best.genes),
                "operators": [g.operator.value for g in best.genes]
            },
            "fitness_distribution": {
                "mean": float(np.mean([g.fitness for g in domain_layer.infogenomes])),
                "std": float(np.std([g.fitness for g in domain_layer.infogenomes])),
                "max": float(max(g.fitness for g in domain_layer.infogenomes)),
                "min": float(min(g.fitness for g in domain_layer.infogenomes))
            }
        }
    
    @app.get("/domain/infogenome/best")
    async def get_best_infogenome():
        """Get the best-performing Infogenome."""
        if not domain_layer.infogenomes:
            raise HTTPException(status_code=404, detail="No Infogenomes available")
        
        best = max(domain_layer.infogenomes, key=lambda g: g.fitness)
        
        return {
            "id": best.id,
            "fitness": best.fitness,
            "genes": [
                {
                    "operator": gene.operator.value,
                    "params": gene.params,
                    "weight": gene.weight,
                    "constraints": gene.constraints
                }
                for gene in best.genes
            ],
            "governance": best.governance,
            "metadata": best.metadata
        }
    
    # ========================
    # Domain Layer Status
    # ========================
    
    @app.get("/domain/status")
    async def get_domain_layer_status():
        """Get comprehensive Domain Layer status and metrics."""
        return {
            "status": "operational",
            "adapters": list(domain_layer.adapters.keys()),
            "statistics": {
                "resonits": len(domain_layer.resonits),
                "resonats": len(domain_layer.resonats),
                "meshes": len(domain_layer.meshes),
                "infogenomes": len(domain_layer.infogenomes)
            },
            "metrics": domain_layer.metrics,
            "best_infogenome_fitness": max(
                (g.fitness for g in domain_layer.infogenomes),
                default=0.0
            ),
            "storage_path": str(domain_layer.storage_path),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @app.get("/domain/topology/torus")
    async def get_torus_coupling():
        """
        Get information about the Torus coupling between Core and Domain layers.
        
        The Mandorla (Vesica Piscis) serves as the gate region.
        """
        return {
            "topology": "Torus T² = S¹_ρ × S¹_ω",
            "coupling_region": "Mandorla (Vesica Piscis)",
            "dimensions": {
                "rho_cycle": "Coherence circulation",
                "omega_cycle": "Rhythm circulation"
            },
            "gate_criteria": {
                "proof_of_resonance": "Required",
                "path_invariance": "ΔPI ≤ ε",
                "coherence": "Φ ≥ φ*"
            },
            "metatron_integration": {
                "nodes": 13,
                "embedding_available": True,
                "triangulation_enhanced": True
            }
        }


# ========================
# Helper Functions
# ========================

async def persist_domain_artifacts(domain_layer: DomainLayer, result: Dict[str, Any]):
    """
    Background task to persist domain artifacts.
    
    Args:
        domain_layer: Domain layer instance
        result: Processing result to persist
    """
    try:
        # Save Resonat
        resonat_path = domain_layer.storage_path / "resonats" / f"{result['resonat']['id']}.json"
        resonat_path.parent.mkdir(exist_ok=True)
        with open(resonat_path, 'w') as f:
            json.dump(result["resonat"], f, indent=2)
        
        # Save MeshHolo
        mesh_path = domain_layer.storage_path / "meshes" / f"{result['mesh']['id']}.json"
        mesh_path.parent.mkdir(exist_ok=True)
        with open(mesh_path, 'w') as f:
            json.dump(result["mesh"], f, indent=2)
        
        # Save Domain TIC
        tic_path = domain_layer.storage_path / "tics" / f"{result['tic']['tic_id']}.json"
        tic_path.parent.mkdir(exist_ok=True)
        with open(tic_path, 'w') as f:
            json.dump(result["tic"], f, indent=2)
        
    except Exception as e:
        print(f"Failed to persist domain artifacts: {e}")


def export_mesh_as_obj(mesh: MeshHolo) -> str:
    """
    Export MeshHolo as Wavefront OBJ format.
    
    Args:
        mesh: MeshHolo to export
        
    Returns:
        OBJ file content as string
    """
    lines = ["# MeshHolo Export"]
    lines.append(f"# Mesh ID: {mesh.id}")
    lines.append("")
    
    # Export vertices
    for vertex in mesh.vertices:
        theta = vertex["theta"]
        chi = vertex["chi"]
        # Convert to 3D coordinates
        x = np.cos(theta) * np.sin(chi)
        y = np.sin(theta) * np.sin(chi)
        z = np.cos(chi)
        lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
    
    lines.append("")
    
    # Export faces (from simplices)
    vertex_ids = {v["id"]: i + 1 for i, v in enumerate(mesh.vertices)}
    for simplex in mesh.simplices:
        if len(simplex) >= 3:
            indices = [str(vertex_ids.get(vid, 1)) for vid in simplex[:3]]
            lines.append(f"f {' '.join(indices)}")
    
    return "\n".join(lines)


def export_mesh_as_ply(mesh: MeshHolo) -> str:
    """
    Export MeshHolo as PLY format.
    
    Args:
        mesh: MeshHolo to export
        
    Returns:
        PLY file content as string
    """
    lines = ["ply"]
    lines.append("format ascii 1.0")
    lines.append(f"comment MeshHolo ID: {mesh.id}")
    lines.append(f"element vertex {len(mesh.vertices)}")
    lines.append("property float x")
    lines.append("property float y")
    lines.append("property float z")
    lines.append("property float psi")
    lines.append("property float rho")
    lines.append("property float omega")
    lines.append("end_header")
    
    # Export vertices with sigma values
    for vertex in mesh.vertices:
        theta = vertex["theta"]
        chi = vertex["chi"]
        sigma = vertex["sigma"]
        
        # Convert to 3D
        x = np.cos(theta) * np.sin(chi)
        y = np.sin(theta) * np.sin(chi)
        z = np.cos(chi)
        
        lines.append(f"{x:.6f} {y:.6f} {z:.6f} {sigma['psi']:.3f} {sigma['rho']:.3f} {sigma['omega']:.3f}")
    
    return "\n".join(lines)