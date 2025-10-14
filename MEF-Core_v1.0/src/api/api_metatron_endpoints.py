"""
api_metatron_endpoints.py
-------------------------

REST API endpoints for Metatron Router integration in MEF-Core.
Provides access to topological routing, transformation services,
and pipeline orchestration with full Metatron Cube capabilities.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import io

# Import MEF-Core with Metatron integration
from src.mef_core_pipeline import (
    MEFCorePipeline,
    SpiralSnapshot,
    TICCandidate
)
from src.topology.metatron_router import (
    MetatronRouter,
    RouteSpec,
    TransformationResult,
    OperatorType
)
from src.gates.merkaba_gate import MerkabaGate


# ========================
# Pydantic Models
# ========================

class ProcessRequest(BaseModel):
    """Request model for processing data through MEF-Core pipeline."""
    raw_input: Any = Field(..., description="Raw input data to process")
    input_type: str = Field(default="json", description="Type of input data")
    target_properties: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional target properties for route optimization"
    )
    use_cached_route: bool = Field(
        default=True,
        description="Whether to use cached routes if available"
    )


class RouteSelectionRequest(BaseModel):
    """Request model for optimal route selection."""
    input_vector: List[float] = Field(
        ..., 
        description="Input vector for transformation (will be padded to 13 dims)"
    )
    target_properties: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Target properties to optimize for"
    )


class TransformRequest(BaseModel):
    """Request model for direct transformation."""
    input_vector: List[float] = Field(..., description="Input vector")
    route_id: Optional[str] = Field(
        default=None,
        description="Specific route ID to use (if None, selects optimal)"
    )
    operator_sequence: Optional[List[str]] = Field(
        default=None,
        description="Custom operator sequence override"
    )


class TopologyQueryRequest(BaseModel):
    """Request model for topology queries."""
    node_id: Optional[int] = Field(
        default=None,
        description="Specific node to query (1-13)"
    )
    edge_type: Optional[str] = Field(
        default=None,
        description="Filter edges by type"
    )
    symmetry_group: Optional[str] = Field(
        default=None,
        description="Query specific symmetry group (C6, D6, S7)"
    )


# ========================
# API Extension Functions
# ========================

def create_metatron_api(app: FastAPI):
    """
    Create comprehensive Metatron Router API endpoints.
    
    Args:
        app: FastAPI application instance
    """
    
    # Initialize MEF-Core pipeline with Metatron
    pipeline = MEFCorePipeline(
        seed="MEF_CORE_API",
        storage_path="C:/MEF/store",
        ledger_path="C:/MEF/ledger",
        metatron_cache=True
    )
    
    # Initialize standalone components for direct access
    metatron_router = pipeline.metatron_router
    merkaba_gate = MerkabaGate()
    
    # ========================
    # Pipeline Endpoints
    # ========================
    
    @app.post("/pipeline/process")
    async def process_through_pipeline(
        request: ProcessRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Process raw input through complete MEF-Core pipeline with Metatron routing.
        
        This endpoint orchestrates the entire transformation:
        Acquisition → Ingestion → Spiral → Metatron Router → 
        Solve-Coagula → TIC Generation
        """
        try:
            # Process through pipeline
            tic_candidate = pipeline.process(
                raw_input=request.raw_input,
                input_type=request.input_type,
                target_properties=request.target_properties
            )
            
            # Prepare response
            response = {
                "tic_id": tic_candidate.tic_id,
                "fixpoint": tic_candidate.fixpoint,
                "route": {
                    "route_id": tic_candidate.metatron_route.route_id,
                    "symmetry_group": tic_candidate.metatron_route.symmetry_group,
                    "score": tic_candidate.metatron_route.score,
                    "operators": tic_candidate.operator_sequence
                },
                "metrics": tic_candidate.transformation_metrics,
                "proof": tic_candidate.proof,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Schedule Merkaba Gate evaluation in background
            background_tasks.add_task(
                evaluate_with_merkaba,
                tic_candidate
            )
            
            return response
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline processing failed: {str(e)}"
            )
    
    @app.get("/pipeline/metrics")
    async def get_pipeline_metrics():
        """Get comprehensive pipeline metrics including Metatron topology."""
        return pipeline.get_pipeline_metrics()
    
    # ========================
    # Metatron Router Endpoints
    # ========================
    
    @app.post("/metatron/route/select")
    async def select_optimal_route(request: RouteSelectionRequest):
        """
        Select optimal transformation route through Metatron topology.
        
        Evaluates multiple paths through the 5040-permutation space
        and returns the route with highest resonance score.
        """
        try:
            # Convert to numpy array
            input_vector = np.array(request.input_vector)
            
            # Select optimal route
            route_spec = metatron_router.select_optimal_route(
                input_vector,
                request.target_properties
            )
            
            return {
                "route_id": route_spec.route_id,
                "permutation": list(route_spec.permutation),
                "operator_sequence": [op.value for op in route_spec.operator_sequence],
                "symmetry_group": route_spec.symmetry_group,
                "score": route_spec.score,
                "metadata": route_spec.metadata
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Route selection failed: {str(e)}"
            )
    
    @app.post("/metatron/transform")
    async def apply_transformation(request: TransformRequest):
        """
        Apply transformation through Metatron topology.
        
        Uses specified route or selects optimal route if not provided.
        """
        try:
            input_vector = np.array(request.input_vector)
            
            # Build route spec if custom sequence provided
            route_spec = None
            if request.operator_sequence:
                # Create custom route from operator sequence
                operators = [OperatorType[op] for op in request.operator_sequence]
                route_spec = RouteSpec(
                    route_id=request.route_id or str(uuid.uuid4()),
                    permutation=tuple(range(1, 14)),  # Identity permutation
                    operator_sequence=operators,
                    symmetry_group="Custom",
                    score=0.0,
                    metadata={"custom": True}
                )
            elif request.route_id:
                # Try to retrieve cached route
                cache_key = request.route_id
                if cache_key in metatron_router.route_cache:
                    route_spec = metatron_router.route_cache[cache_key]
            
            # Apply transformation
            result = metatron_router.transform(input_vector, route_spec)
            
            return {
                "input": result.input_vector.tolist(),
                "output": result.output_vector.tolist(),
                "route": {
                    "route_id": result.route_spec.route_id,
                    "operators": [op.value for op in result.route_spec.operator_sequence],
                    "score": result.route_spec.score
                },
                "metrics": result.resonance_metrics,
                "convergence": result.convergence_data,
                "timestamp": result.timestamp
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Transformation failed: {str(e)}"
            )
    
    @app.get("/metatron/topology/nodes")
    async def get_topology_nodes(
        node_id: Optional[int] = Query(None, ge=1, le=13),
        node_type: Optional[str] = Query(None)
    ):
        """
        Get Metatron Cube nodes information.
        
        Returns information about the 13 canonical nodes including
        coordinates, types, and topological properties.
        """
        nodes = metatron_router.metatron.list_nodes(type=node_type)
        
        if node_id:
            # Filter to specific node
            nodes = [n for n in nodes if n["id"] == node_id]
        
        return {
            "nodes": nodes,
            "count": len(nodes),
            "topology": "Metatron Cube (13 nodes)"
        }
    
    @app.get("/metatron/topology/edges")
    async def get_topology_edges(
        edge_type: Optional[str] = Query(None),
        full_connectivity: bool = Query(False)
    ):
        """
        Get Metatron Cube edges information.
        
        Returns edge list with optional filtering by type.
        """
        edges = metatron_router.metatron.list_edges(type=edge_type)
        
        return {
            "edges": edges,
            "count": len(edges),
            "full_connectivity": full_connectivity,
            "max_edges": 78  # Complete graph on 13 nodes
        }
    
    @app.get("/metatron/symmetry/{group}")
    async def get_symmetry_group(
        group: str,
        limit: int = Query(10, le=100)
    ):
        """
        Get permutations from specific symmetry group.
        
        Available groups: C6 (cyclic), D6 (dihedral), S7 (symmetric)
        """
        try:
            if group.upper() not in ["C6", "D6", "S7"]:
                raise ValueError(f"Unknown symmetry group: {group}")
            
            operators = metatron_router.metatron.enumerate_group(group.upper())
            
            # Limit results for S7 (5040 permutations)
            operators = operators[:limit]
            
            return {
                "group": group.upper(),
                "operators": operators,
                "count": len(operators),
                "total_in_group": {
                    "C6": 6,
                    "D6": 12,
                    "S7": 5040
                }.get(group.upper(), 0)
            }
            
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Symmetry group query failed: {str(e)}"
            )
    
    @app.get("/metatron/operators")
    async def list_available_operators():
        """
        List all available MEF-Core operators.
        
        Returns the four core operators (DK, SW, PI, WT) with descriptions.
        """
        return {
            "operators": [
                {
                    "code": "DK",
                    "name": "DoubleKick",
                    "description": "Applies orthogonal impulses to escape local minima",
                    "properties": ["non-expansive", "deterministic"]
                },
                {
                    "code": "SW",
                    "name": "Sweep",
                    "description": "Adaptive threshold sweep based on resonance",
                    "properties": ["non-expansive", "adaptive"]
                },
                {
                    "code": "PI",
                    "name": "PathInvariance",
                    "description": "Projects to canonical form for path invariance",
                    "properties": ["idempotent", "non-expansive"]
                },
                {
                    "code": "WT",
                    "name": "WeightTransfer",
                    "description": "Redistributes weights across topological scales",
                    "properties": ["conservative", "multi-scale"]
                }
            ],
            "composition": "Operators can be composed in any sequence",
            "total_permutations": 5040
        }
    
    @app.post("/metatron/resonance/calculate")
    async def calculate_resonance(
        vectors: List[List[float]],
        use_mandorla: bool = True
    ):
        """
        Calculate resonance metrics for given vectors.
        
        Uses Mandorla field and QLOGIC spectral analysis.
        """
        try:
            if use_mandorla:
                # Use Mandorla field
                metatron_router.mandorla.clear_inputs()
                for vec in vectors:
                    vec_array = np.array(vec)
                    # Truncate or pad to 5 dimensions for Mandorla
                    if len(vec_array) > 5:
                        vec_array = vec_array[:5]
                    elif len(vec_array) < 5:
                        vec_array = np.pad(vec_array, (0, 5 - len(vec_array)))
                    metatron_router.mandorla.add_input(vec_array)
                
                resonance = metatron_router.mandorla.calc_resonance()
                entropy = metatron_router.mandorla.calc_entropy()
                variance = metatron_router.mandorla.calc_variance()
                
                return {
                    "resonance": float(resonance),
                    "entropy": float(entropy),
                    "variance": float(variance),
                    "method": "Mandorla Field",
                    "vector_count": len(vectors)
                }
            else:
                # Use direct resonance calculation
                resonances = []
                for vec in vectors:
                    vec_array = metatron_router._pad_to_metatron_dims(np.array(vec))
                    res = metatron_router._calculate_resonance(vec_array)
                    resonances.append(float(res))
                
                return {
                    "resonances": resonances,
                    "mean": float(np.mean(resonances)),
                    "std": float(np.std(resonances)),
                    "method": "Direct Spectral",
                    "vector_count": len(vectors)
                }
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Resonance calculation failed: {str(e)}"
            )
    
    @app.get("/metatron/cache/status")
    async def get_cache_status():
        """Get Metatron route cache status and statistics."""
        cache_info = {
            "enabled": metatron_router.cache_enabled,
            "cached_routes": len(metatron_router.route_cache),
            "storage_path": str(metatron_router.storage_path),
            "cache_keys": list(metatron_router.route_cache.keys())[:10]  # First 10
        }
        
        # Calculate cache statistics
        if metatron_router.route_cache:
            scores = [route.score for route in metatron_router.route_cache.values()]
            cache_info["statistics"] = {
                "mean_score": float(np.mean(scores)),
                "max_score": float(np.max(scores)),
                "min_score": float(np.min(scores))
            }
        
        return cache_info
    
    @app.delete("/metatron/cache/clear")
    async def clear_route_cache():
        """Clear Metatron route cache."""
        count = len(metatron_router.route_cache)
        metatron_router.route_cache.clear()
        
        # Save cleared cache
        metatron_router._save_route_cache()
        
        return {
            "status": "cleared",
            "routes_removed": count
        }
    
    @app.get("/metatron/export/{route_id}")
    async def export_route(
        route_id: str,
        format: str = Query("json", regex="^(json|dot)$")
    ):
        """
        Export specific route in requested format.
        
        Formats: json (structured data), dot (GraphViz visualization)
        """
        # Find route in cache
        route_spec = None
        for key, route in metatron_router.route_cache.items():
            if route.route_id == route_id:
                route_spec = route
                break
        
        if not route_spec:
            raise HTTPException(
                status_code=404,
                detail=f"Route {route_id} not found"
            )
        
        # Export in requested format
        export_data = metatron_router.export_route_graph(route_spec, format)
        
        if format == "dot":
            # Return as downloadable file
            return StreamingResponse(
                io.BytesIO(export_data.encode()),
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=route_{route_id[:8]}.dot"
                }
            )
        else:
            return JSONResponse(content=json.loads(export_data))
    
    # ========================
    # Integration Status Endpoint
    # ========================
    
    @app.get("/status/integration")
    async def get_integration_status():
        """
        Get complete MEF-Core and Metatron integration status.
        
        Returns comprehensive status of all integrated components.
        """
        return {
            "status": "operational",
            "components": {
                "mef_core": {
                    "status": "active",
                    "pipeline_metrics": pipeline.metrics
                },
                "metatron_router": {
                    "status": "active",
                    "topology": metatron_router.get_topology_metrics()
                },
                "merkaba_gate": {
                    "status": "active",
                    "thresholds": {
                        "epsilon": merkaba_gate.epsilon,
                        "phi_star": merkaba_gate.phi_star,
                        "eta": merkaba_gate.eta
                    }
                },
                "storage": {
                    "spiral": pipeline.spiral_storage.count(),
                    "routes_cached": len(metatron_router.route_cache)
                }
            },
            "configuration": {
                "seed": pipeline.seed,
                "storage_path": str(pipeline.storage_path),
                "ledger_path": str(pipeline.ledger_path),
                "full_edges": True
            },
            "timestamp": datetime.utcnow().isoformat()
        }


async def evaluate_with_merkaba(tic_candidate: TICCandidate):
    """
    Background task to evaluate TIC with Merkaba Gate.
    
    Args:
        tic_candidate: TIC candidate to evaluate
    """
    try:
        # Convert TIC candidate to format expected by Merkaba
        merkaba_gate = MerkabaGate()
        
        # Mock snapshot ID (in production, retrieve actual snapshot)
        snapshot_id = tic_candidate.source_snapshot
        
        # Run Merkaba evaluation
        gate_result = merkaba_gate.run_merkaba(
            snapshot_id=snapshot_id,
            tic_candidate_id=tic_candidate.tic_id
        )
        
        # Log result
        print(f"Merkaba Gate evaluation for {tic_candidate.tic_id}: {gate_result['decision']}")
        
    except Exception as e:
        print(f"Merkaba evaluation failed: {e}")