"""
MEF-Core Command Line Interface
CLI for interacting with the MEF-Core system.
"""

import click
import json
import yaml
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import requests
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from spiral.snapshot import SpiralSnapshot
from spiral.storage import SpiralStorage
from spiral.proof_of_resonance import ProofOfResonance
from solvecoagula.operators import SolveCoagula
from tic.crystallizer import TICCrystallizer
from ledger.mef_block import MEFLedger
from hdag.graph import HDAG
from ingestion.triton_core import TritonCore

# Default paths
DEFAULT_CONFIG = Path("config.yaml")
DEFAULT_STORE = Path(os.getenv("MEF_STORE_DIR", str(Path.home() / "mef" / "store")))
DEFAULT_LEDGER = Path(os.getenv("MEF_LEDGER_DIR", str(Path.home() / "mef" / "ledger")))
DEFAULT_API_URL = os.getenv("MEF_API_URL", "http://localhost:8000")

@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), default=str(DEFAULT_CONFIG),
              help='Configuration file path')
@click.option('--api-url', default=DEFAULT_API_URL, help='API server URL')
@click.pass_context
def cli(ctx, config, api_url):
    """MEF-Core Command Line Interface"""
    ctx.ensure_object(dict)
    
    # Load configuration
    config_path = Path(config)
    if config_path.exists():
        with open(config_path, 'r') as f:
            ctx.obj['config'] = yaml.safe_load(f)
    else:
        click.echo(f"Warning: Config file {config} not found, using defaults", err=True)
        ctx.obj['config'] = {
            "seed": "MEF_SEED_42",
            "spiral": {"r": 1.0, "a": 0.05, "b": 0.2, "c": 0.2, "k": 2, "step": 0.01},
            "solvecoagula": {"lambda": 0.8, "eps": 1e-6, "max_iter": 1000}
        }
    
    ctx.obj['api_url'] = api_url

@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--type', '-t', default='raw', 
              type=click.Choice(['text', 'json', 'numeric', 'binary', 'raw']),
              help='Data type')
@click.option('--seed', '-s', default='MEF_SEED_42', help='Deterministic seed')
@click.option('--local/--remote', default=False, help='Use local processing or API')
@click.pass_context
def ingest(ctx, file_path, type, seed, local):
    """Ingest a file into the MEF-Core system"""
    
    # Read file
    file_path = Path(file_path)
    if type == 'binary':
        with open(file_path, 'rb') as f:
            data = f.read()
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = f.read()
    
    if type == 'json':
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            click.echo("Error: Invalid JSON file", err=True)
            sys.exit(1)
    
    if local:
        # Local processing
        config = ctx.obj['config']
        
        # Initialize components
        triton = TritonCore(config)
        spiral = SpiralSnapshot(config.get('spiral', {}), str(DEFAULT_STORE))
        storage = SpiralStorage(str(DEFAULT_STORE))
        
        # Process
        normalized = triton.normalize(data, type)
        snapshot = spiral.create_snapshot(normalized, seed)
        file_saved = spiral.save_snapshot(snapshot)
        storage.store_snapshot(snapshot)
        
        click.echo(f"✓ Snapshot created: {snapshot['id']}")
        click.echo(f"  Phase: {snapshot['phase']:.4f}")
        click.echo(f"  PoR: {snapshot['metrics']['por']}")
        click.echo(f"  File: {file_saved}")
    else:
        # Remote API processing
        api_url = ctx.obj['api_url']
        
        response = requests.post(
            f"{api_url}/ingest",
            json={
                "data": data if isinstance(data, (dict, list)) else str(data),
                "data_type": type,
                "seed": seed
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"✓ Snapshot created: {result['snapshot_id']}")
            click.echo(f"  Phase: {result['phase']:.4f}")
            click.echo(f"  PoR: {result['por']}")
        else:
            click.echo(f"Error: {response.text}", err=True)
            sys.exit(1)

@cli.command()
@click.argument('snapshot_id')
@click.option('--commit/--no-commit', default=False, help='Auto-commit to ledger')
@click.option('--local/--remote', default=False, help='Use local processing or API')
@click.pass_context
def process(ctx, snapshot_id, commit, local):
    """Process a snapshot through Solve-Coagula to create TIC"""
    
    if local:
        config = ctx.obj['config']
        
        # Initialize components
        storage = SpiralStorage(str(DEFAULT_STORE))
        solve_coagula = SolveCoagula(config.get('solvecoagula', {}))
        tic_crystallizer = TICCrystallizer(config, str(DEFAULT_STORE))
        ledger = MEFLedger(str(DEFAULT_LEDGER))
        
        # Load snapshot
        snapshot = storage.retrieve_snapshot(snapshot_id)
        if not snapshot:
            click.echo(f"Error: Snapshot {snapshot_id} not found", err=True)
            sys.exit(1)
        
        # Process
        coordinates = np.array(snapshot['coordinates'])
        fixpoint, convergence_info = solve_coagula.iterate_to_fixpoint(coordinates, True)
        
        # Create TIC
        tic = tic_crystallizer.create_tic(
            fixpoint, snapshot['id'], snapshot['seed'],
            convergence_info, snapshot
        )
        tic_crystallizer.save_tic(tic)
        storage.store_tic(tic)
        
        click.echo(f"✓ TIC created: {tic['tic_id']}")
        click.echo(f"  Converged: {convergence_info['converged']}")
        click.echo(f"  Iterations: {convergence_info['iterations']}")
        
        # Check commit
        should_commit = tic_crystallizer.should_commit(tic)
        click.echo(f"  Should commit: {should_commit}")
        
        if should_commit and commit:
            success, result = ledger.append_block(tic, snapshot)
            if success:
                click.echo(f"✓ Committed to ledger: Block #{result['index']}")
            else:
                click.echo(f"Error committing: {result.get('error')}", err=True)
    else:
        # Remote API processing
        api_url = ctx.obj['api_url']
        
        response = requests.post(
            f"{api_url}/process",
            json={
                "snapshot_id": snapshot_id,
                "auto_commit": commit
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"✓ TIC created: {result['tic_id']}")
            click.echo(f"  Converged: {result['fixpoint_converged']}")
            click.echo(f"  Iterations: {result['iterations']}")
            click.echo(f"  Should commit: {result['should_commit']}")
            if result['committed']:
                click.echo(f"✓ Committed to ledger: Block #{result['block_index']}")
        else:
            click.echo(f"Error: {response.text}", err=True)
            sys.exit(1)

@cli.command()
@click.option('--start', '-s', type=int, default=0, help='Start block index')
@click.option('--export', '-e', is_flag=True, help='Export audit trail')
@click.option('--local/--remote', default=False, help='Use local processing or API')
@click.pass_context
def audit(ctx, start, export, local):
    """Audit the MEF ledger integrity"""
    
    if local:
        ledger = MEFLedger(str(DEFAULT_LEDGER))
        
        click.echo("Auditing ledger...")
        is_valid = ledger.verify_chain_integrity(start)
        stats = ledger.get_chain_statistics()
        
        click.echo(f"Chain valid: {'✓' if is_valid else '✗'}")
        click.echo(f"Total blocks: {stats['total_blocks']}")
        click.echo(f"Chain size: {stats['total_size_mb']:.2f} MB")
        
        if stats['time_range']['first']:
            click.echo(f"First block: {stats['time_range']['first']}")
            click.echo(f"Last block: {stats['time_range']['last']}")
        
        if export:
            export_path = ledger.export_audit_trail()
            click.echo(f"✓ Audit trail exported to: {export_path}")
    else:
        # Remote API
        api_url = ctx.obj['api_url']
        
        response = requests.post(
            f"{api_url}/audit",
            json={
                "start_index": start,
                "export": export
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"Chain valid: {'✓' if result['chain_valid'] else '✗'}")
            stats = result['statistics']
            click.echo(f"Total blocks: {stats['total_blocks']}")
            click.echo(f"Chain size: {stats['total_size_mb']:.2f} MB")
            
            if export and 'export_path' in result:
                click.echo(f"✓ Audit trail exported to: {result['export_path']}")
        else:
            click.echo(f"Error: {response.text}", err=True)
            sys.exit(1)

@cli.command()
@click.argument('snapshot_id')
@click.option('--local/--remote', default=False, help='Use local processing or API')
@click.pass_context
def validate(ctx, snapshot_id, local):
    """Validate a snapshot using Proof-of-Resonance"""
    
    if local:
        config = ctx.obj['config']
        storage = SpiralStorage(str(DEFAULT_STORE))
        por_validator = ProofOfResonance(config)
        
        snapshot = storage.retrieve_snapshot(snapshot_id)
        if not snapshot:
            click.echo(f"Error: Snapshot {snapshot_id} not found", err=True)
            sys.exit(1)
        
        is_valid, report = por_validator.validate_snapshot(snapshot)
        
        click.echo(f"Snapshot: {snapshot_id}")
        click.echo(f"Valid: {'✓' if is_valid else '✗'}")
        click.echo(f"Resonance:")
        click.echo(f"  FFT: {report['resonance']['fft_resonance']:.4f}")
        click.echo(f"  Claimed: {report['resonance']['claimed_resonance']:.4f}")
        click.echo(f"  Deviation: {report['resonance']['deviation']:.4f}")
        click.echo(f"  Spectral gap: {report['resonance']['spectral_gap']:.4f}")
        click.echo(f"Stability:")
        click.echo(f"  Computed: {report['stability']['computed']:.4f}")
        click.echo(f"  Valid: {'✓' if report['stability']['valid'] else '✗'}")
    else:
        # Remote API
        api_url = ctx.obj['api_url']
        
        response = requests.post(f"{api_url}/validate/snapshot/{snapshot_id}")
        
        if response.status_code == 200:
            report = response.json()
            click.echo(f"Snapshot: {report['snapshot_id']}")
            click.echo(f"Valid: {'✓' if report['overall_valid'] else '✗'}")
            click.echo(f"Resonance:")
            click.echo(f"  FFT: {report['resonance']['fft_resonance']:.4f}")
            click.echo(f"  Claimed: {report['resonance']['claimed_resonance']:.4f}")
            click.echo(f"  Deviation: {report['resonance']['deviation']:.4f}")
            click.echo(f"  Spectral gap: {report['resonance']['spectral_gap']:.4f}")
            click.echo(f"Stability:")
            click.echo(f"  Computed: {report['stability']['computed']:.4f}")
            click.echo(f"  Valid: {'✓' if report['stability']['valid'] else '✗'}")
        else:
            click.echo(f"Error: {response.text}", err=True)
            sys.exit(1)

@cli.command()
@click.option('--format', '-f', type=click.Choice(['json', 'audit']), default='json',
              help='Export format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.pass_context
def export(ctx, format, output):
    """Export system data"""
    
    api_url = ctx.obj['api_url']
    
    response = requests.get(f"{api_url}/export/{format}")
    
    if response.status_code == 200:
        if output:
            output_path = Path(output)
            if format == 'json':
                with open(output_path, 'w') as f:
                    json.dump(response.json(), f, indent=2)
            else:
                with open(output_path, 'wb') as f:
                    f.write(response.content)
            click.echo(f"✓ Exported to: {output_path}")
        else:
            if format == 'json':
                click.echo(json.dumps(response.json(), indent=2))
            else:
                click.echo(response.text)
    else:
        click.echo(f"Error: {response.text}", err=True)
        sys.exit(1)

@cli.command()
@click.option('--seed', '-s', default='MEF_SEED_42', help='Deterministischer Seed')
@click.option('--in', 'input_file', required=True, type=click.Path(exists=True), help='Eingabedatei')
@click.option('--out', 'output_path', default='C:/MEF/store', help='Ausgabepfad')
def embed(seed, input_file, output_path):
    """SPEC-002: Embed-Befehl für Spiral-Einbettung"""
    import json
    from pathlib import Path
    
    # Lade Daten
    input_path = Path(input_file)
    if input_path.suffix == '.json':
        with open(input_path, 'r') as f:
            data = json.load(f)
    else:
        with open(input_path, 'r') as f:
            data = f.read()
    
    # API-Aufruf
    api_url = "http://localhost:8000"
    response = requests.post(
        f"{api_url}/acquisition",
        json=data if isinstance(data, dict) else {"data": data}
    )
    
    if response.status_code == 200:
        result = response.json()
        click.echo(f"✓ Snapshot erstellt: {result['snapshot_id']}")
        click.echo(f"  Phase: {result['phase']}")
        click.echo(f"  PoR: {result['por']}")
        click.echo(f"  Gespeichert: {output_path}")
    else:
        click.echo(f"Fehler: {response.text}", err=True)
        sys.exit(1)

@cli.command()
@click.option('--snapshot', required=True, help='Snapshot ID')
@click.option('--out', 'output_file', help='Ausgabe TIC Datei')
def solve(snapshot, output_file):
    """SPEC-002: Solve-Befehl für Fixpunkt-Berechnung"""
    api_url = "http://localhost:8000"
    response = requests.post(f"{api_url}/solve?snapshot_id={snapshot}")
    
    if response.status_code == 200:
        result = response.json()
        click.echo(f"✓ TIC erstellt: {result['tic_id']}")
        click.echo(f"  Status: {result['status']}")
        click.echo(f"  Schritte: {result['steps']}")
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(result, f, indent=2)
            click.echo(f"  Gespeichert: {output_file}")
    else:
        click.echo(f"Fehler: {response.text}", err=True)
        sys.exit(1)

@cli.command()
@click.argument('subcommand', type=click.Choice(['append', 'verify']))
@click.option('--tic', help='TIC ID für append')
@click.option('--snapshot', help='Snapshot ID für append')
@click.option('--verify', is_flag=True, help='Ledger verifizieren')
def ledger(subcommand, tic, snapshot, verify):
    """SPEC-002: Ledger-Befehle"""
    api_url = "http://localhost:8000"
    
    if subcommand == 'append':
        if not tic or not snapshot:
            click.echo("Fehler: --tic und --snapshot erforderlich für append", err=True)
            sys.exit(1)
        
        response = requests.post(
            f"{api_url}/ledger",
            params={"tic_id": tic, "snapshot_id": snapshot}
        )
        
        if response.status_code == 200:
            result = response.json()
            click.echo(f"✓ Block hinzugefügt: #{result['index']}")
            click.echo(f"  Hash: {result['hash']}")
            click.echo(f"  Previous: {result['previous_hash']}")
        else:
            click.echo(f"Fehler: {response.text}", err=True)
            sys.exit(1)
    
    elif subcommand == 'verify' or verify:
        # Ledger-Verifikation lokal
        from ledger.mef_block import MEFLedger
        ledger = MEFLedger("C:/MEF/ledger")
        is_valid = ledger.verify_chain_integrity()
        
        if is_valid:
            click.echo("✓ Ledger-Integrität verifiziert")
        else:
            click.echo("✗ Ledger-Integrität verletzt!", err=True)
            sys.exit(1)

@cli.command()
@click.option('--verify', is_flag=True, help='Audit-Verifikation')
def audit(verify):
    """SPEC-002: Audit-Befehl"""
    if verify:
        # Verifiziere Ledger-Integrität
        from ledger.mef_block import MEFLedger
        ledger = MEFLedger("C:/MEF/ledger")
        is_valid = ledger.verify_chain_integrity()
        
        if is_valid:
            click.echo("✓ Audit erfolgreich: Ledger integer")
        else:
            click.echo("✗ Audit fehlgeschlagen: Ledger korrupt", err=True)
            sys.exit(1)
    else:
        # Download Audit-ZIP
        api_url = "http://localhost:8000"
        response = requests.get(f"{api_url}/audit")
        
        if response.status_code == 200:
            filename = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            with open(filename, 'wb') as f:
                f.write(response.content)
            click.echo(f"✓ Audit exportiert: {filename}")
        else:
            click.echo(f"Fehler: {response.text}", err=True)
            sys.exit(1)

@cli.command()
@click.pass_context
def ping(ctx):
    """Ping the API server"""
    
    api_url = ctx.obj['api_url']
    
    try:
        response = requests.get(f"{api_url}/ping")
        if response.status_code == 200:
            data = response.json()
            click.echo("✓ API server is operational")
            click.echo(f"  Version: {data['version']}")
            click.echo(f"  Seed: {data['seed']}")
            click.echo(f"  Timestamp: {data['timestamp']}")
        else:
            click.echo(f"✗ API server error: {response.status_code}", err=True)
    except requests.exceptions.ConnectionError:
        click.echo(f"✗ Cannot connect to API server at {api_url}", err=True)
        sys.exit(1)

if __name__ == "__main__":
    cli(obj={})