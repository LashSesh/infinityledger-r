"""
api_merkaba_integration.py
--------------------------

API server extensions for Merkaba Gate integration.
Adds endpoints and CLI commands for gate evaluation and ledger commitment.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import click
import json
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

# Import core components
from src.gates.merkaba_gate import MerkabaGate, validate_gate_event
from src.ledger import Ledger  # Assuming ledger module exists
from src.hdag.graph import HDAG


# ========================
# API Models
# ========================

class MerkabaGateRequest(BaseModel):
    """Request model for Merkaba Gate evaluation."""
    snapshot_id: str = Field(..., description="Snapshot identifier")
    tic_candidate_id: str = Field(..., description="TIC candidate identifier")
    params: Optional[Dict[str, float]] = Field(
        default=None,
        description="Optional parameter overrides (epsilon, phi_star, eta)"
    )


class MerkabaGateResponse(BaseModel):
    """Response model for Merkaba Gate evaluation."""
    gate_id: str
    snapshot_id: str
    tic_candidate_id: str
    checks: Dict[str, Any]
    decision: Dict[str, Any]
    timestamp: str
    ledger_block_id: Optional[str] = None


# ========================
# API Server Extension
# ========================

def extend_api_with_merkaba(app: FastAPI, ledger: Ledger, hdag: HDAG):
    """
    Extend existing FastAPI app with Merkaba Gate endpoints.
    
    Args:
        app: FastAPI application instance
        ledger: MEF Ledger instance
        hdag: HDAG graph instance
    """
    
    # Initialize Merkaba Gate
    merkaba_gate = MerkabaGate()
    
    @app.post("/gate/merkaba", response_model=MerkabaGateResponse)
    async def evaluate_merkaba_gate(
        request: MerkabaGateRequest,
        background_tasks: BackgroundTasks
    ):
        """
        Evaluate a TIC candidate through the Merkaba Gate.
        
        If the gate approves (commit=true), the TIC is committed to the ledger.
        All evaluations are audited regardless of outcome.
        """
        try:
            # Run Merkaba Gate evaluation
            gate_event = merkaba_gate.run_merkaba(
                snapshot_id=request.snapshot_id,
                tic_candidate_id=request.tic_candidate_id,
                params=request.params
            )
            
            # Validate event against schema
            if not validate_gate_event(gate_event):
                raise HTTPException(
                    status_code=500,
                    detail="Gate event validation failed"
                )
            
            response = MerkabaGateResponse(**gate_event)
            
            # If commit approved, append to ledger
            if gate_event["decision"]["commit"]:
                # Schedule ledger append in background
                background_tasks.add_task(
                    commit_to_ledger,
                    ledger,
                    hdag,
                    gate_event
                )
                
            return response
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Gate evaluation failed: {str(e)}"
            )
    
    @app.get("/gate/merkaba/status")
    async def get_merkaba_status():
        """Get current Merkaba Gate configuration and status."""
        return {
            "status": "operational",
            "thresholds": {
                "epsilon": merkaba_gate.epsilon,
                "phi_star": merkaba_gate.phi_star,
                "eta": merkaba_gate.eta
            },
            "metatron_nodes": 13,
            "state_history_length": len(merkaba_gate.state_history),
            "audit_path": str(merkaba_gate.audit_path)
        }
    
    @app.get("/gate/merkaba/audit")
    async def get_audit_log(limit: int = 100):
        """Retrieve recent Merkaba Gate audit entries."""
        audit_path = merkaba_gate.audit_path
        
        if not audit_path.exists():
            return {"entries": [], "total": 0}
        
        entries = []
        with open(audit_path, 'r') as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))
        
        # Return most recent entries
        entries = entries[-limit:]
        entries.reverse()  # Most recent first
        
        return {
            "entries": entries,
            "total": len(entries)
        }
    
    @app.post("/gate/merkaba/calibrate")
    async def calibrate_thresholds(
        epsilon: Optional[float] = None,
        phi_star: Optional[float] = None,
        eta: Optional[float] = None
    ):
        """
        Calibrate Merkaba Gate thresholds.
        
        This endpoint allows dynamic adjustment of gate parameters
        without restarting the service.
        """
        updated = {}
        
        if epsilon is not None:
            merkaba_gate.epsilon = epsilon
            updated["epsilon"] = epsilon
        
        if phi_star is not None:
            merkaba_gate.phi_star = phi_star
            updated["phi_star"] = phi_star
        
        if eta is not None:
            merkaba_gate.eta = eta
            updated["eta"] = eta
        
        return {
            "status": "calibrated",
            "updated": updated,
            "current": {
                "epsilon": merkaba_gate.epsilon,
                "phi_star": merkaba_gate.phi_star,
                "eta": merkaba_gate.eta
            }
        }


async def commit_to_ledger(ledger: Ledger, hdag: HDAG, gate_event: Dict[str, Any]):
    """
    Commit approved TIC to ledger and update HDAG.
    
    Args:
        ledger: MEF Ledger instance
        hdag: HDAG graph instance
        gate_event: Approved gate event
    """
    try:
        # Create ledger block with gate proof
        block_data = {
            "tic_id": gate_event["tic_candidate_id"],
            "snapshot_id": gate_event["snapshot_id"],
            "gate_id": gate_event["gate_id"],
            "proof": gate_event["checks"],
            "timestamp": gate_event["timestamp"]
        }
        
        # Append to ledger
        block_id = await ledger.append_block(
            tic_id=gate_event["tic_candidate_id"],
            snapshot_id=gate_event["snapshot_id"],
            data=block_data,
            proof=gate_event["checks"]
        )
        
        # Update HDAG with gate transition
        if hdag:
            hdag_node = hdag.create_node(
                snapshot_id=gate_event["snapshot_id"],
                phase=gate_event["checks"]["phi"],  # Use coherence as phase
                timestamp=gate_event["timestamp"]
            )
            
            # Store gate reference in TIC
            gate_event["hdag_node"] = hdag_node
            gate_event["ledger_block_id"] = block_id
        
        return block_id
        
    except Exception as e:
        # Log error but don't fail the response
        print(f"Ledger commit error: {e}")
        return None


# ========================
# CLI Commands
# ========================

@click.group()
def cli():
    """MEF Merkaba Gate CLI commands."""
    pass


@cli.command()
@click.option('--snapshot', '-s', required=True, help='Snapshot ID')
@click.option('--tic', '-t', required=True, help='TIC candidate ID')
@click.option('--epsilon', '-e', type=float, help='Path invariance threshold')
@click.option('--phi-star', '-p', type=float, help='Coherence threshold')
@click.option('--eta', type=float, help='MCI threshold')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
def merkaba(snapshot, tic, epsilon, phi_star, eta, output):
    """
    Evaluate a TIC candidate through the Merkaba Gate.
    
    Example:
        mef gate merkaba --snapshot S1 --tic T1
        mef gate merkaba -s S1 -t T1 --epsilon 1e-5 -o result.json
    """
    # Initialize gate
    gate = MerkabaGate()
    
    # Build params if provided
    params = {}
    if epsilon is not None:
        params['epsilon'] = epsilon
    if phi_star is not None:
        params['phi_star'] = phi_star
    if eta is not None:
        params['eta'] = eta
    
    # Run evaluation
    try:
        result = gate.run_merkaba(
            snapshot_id=snapshot,
            tic_candidate_id=tic,
            params=params if params else None
        )
        
        # Format output
        output_json = json.dumps(result, indent=2)
        
        # Write to file or stdout
        if output:
            with open(output, 'w') as f:
                f.write(output_json)
            click.echo(f"Gate event written to {output}")
        else:
            click.echo(output_json)
        
        # Show decision summary
        if result['decision']['commit']:
            click.echo(click.style(
                f"\n✓ COMMIT APPROVED: {result['decision']['reason']}",
                fg='green', bold=True
            ))
        else:
            click.echo(click.style(
                f"\n✗ COMMIT REJECTED: {result['decision']['reason']}",
                fg='red', bold=True
            ))
        
    except Exception as e:
        click.echo(click.style(f"Error: {str(e)}", fg='red'), err=True)
        raise click.Abort()


@cli.command()
@click.option('--limit', '-n', type=int, default=10, help='Number of entries to show')
@click.option('--commits-only', is_flag=True, help='Show only committed events')
@click.option('--rejections-only', is_flag=True, help='Show only rejected events')
def audit(limit, commits_only, rejections_only):
    """
    View Merkaba Gate audit log.
    
    Example:
        mef gate audit
        mef gate audit --limit 50 --commits-only
    """
    gate = MerkabaGate()
    audit_path = gate.audit_path
    
    if not audit_path.exists():
        click.echo("No audit log found.")
        return
    
    entries = []
    with open(audit_path, 'r') as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                
                # Filter based on flags
                if commits_only and not entry['decision']['commit']:
                    continue
                if rejections_only and entry['decision']['commit']:
                    continue
                    
                entries.append(entry)
    
    # Get most recent entries
    entries = entries[-limit:]
    entries.reverse()
    
    # Display entries
    for entry in entries:
        # Format timestamp
        timestamp = entry['timestamp'][:19].replace('T', ' ')
        
        # Format decision
        if entry['decision']['commit']:
            decision = click.style('COMMIT', fg='green', bold=True)
        else:
            decision = click.style('REJECT', fg='red', bold=True)
        
        # Format checks
        checks = (
            f"PoR={entry['checks']['por']}, "
            f"ΔPI={entry['checks']['delta_pi']:.6f}, "
            f"Φ={entry['checks']['phi']:.3f}, "
            f"ΔV={entry['checks']['delta_v']:.6f}"
        )
        
        if 'mci' in entry['checks']:
            checks += f", MCI={entry['checks']['mci']:.3f}"
        
        click.echo(f"[{timestamp}] {decision} | {checks}")
        click.echo(f"  Gate: {entry['gate_id']}")
        click.echo(f"  Reason: {entry['decision']['reason']}")
        click.echo()


@cli.command()
@click.option('--epsilon', '-e', type=float, help='Path invariance threshold')
@click.option('--phi-star', '-p', type=float, help='Coherence threshold')
@click.option('--eta', type=float, help='MCI threshold')
def calibrate(epsilon, phi_star, eta):
    """
    Calibrate Merkaba Gate thresholds.
    
    Example:
        mef gate calibrate --epsilon 1e-5
        mef gate calibrate --phi-star 0.7 --eta 0.9
    """
    gate = MerkabaGate()
    
    updated = {}
    
    if epsilon is not None:
        gate.epsilon = epsilon
        updated['epsilon'] = epsilon
    
    if phi_star is not None:
        gate.phi_star = phi_star
        updated['phi_star'] = phi_star
    
    if eta is not None:
        gate.eta = eta
        updated['eta'] = eta
    
    if updated:
        click.echo("Gate thresholds updated:")
        for key, value in updated.items():
            click.echo(f"  {key}: {value}")
    
    click.echo("\nCurrent thresholds:")
    click.echo(f"  epsilon: {gate.epsilon}")
    click.echo(f"  phi_star: {gate.phi_star}")
    click.echo(f"  eta: {gate.eta}")


if __name__ == '__main__':
    cli()