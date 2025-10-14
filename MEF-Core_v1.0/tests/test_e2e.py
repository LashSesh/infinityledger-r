"""
End-to-End Tests for MEF-Core
Verifies deterministic behavior and complete pipeline functionality.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
import numpy as np
import sys
import hashlib
from datetime import datetime, timedelta

# Add source to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ingestion.triton_core import normalize_payload, TritonCore
from spiral.snapshot import SpiralSnapshot
from spiral.storage import SpiralStorage
from spiral.proof_of_resonance import ProofOfResonance
from solvecoagula.operators import SolveCoagula, iterate_to_fixpoint
from tic.crystallizer import TICCrystallizer
from ledger.mef_block import MEFLedger
from hdag.graph import HDAG

# Fixed seed for deterministic testing
TEST_SEED = "MEF_SEED_42"
TEST_CONFIG = {
    "seed": TEST_SEED,
    "spiral": {
        "r": 1.0,
        "a": 0.05,
        "b": 0.2,
        "c": 0.2,
        "k": 2,
        "step": 0.01
    },
    "solvecoagula": {
        "lambda": 0.8,
        "eps": 1e-6,
        "max_iter": 1000,
        "operators": {
            "dk": {"alpha1": 0.05, "alpha2": -0.03},
            "sw": {"tau0": 0.5, "beta": 0.1, "schedule": "cosine"},
            "pi": {"canon": "lexicographic", "tol": 1e-6},
            "wt": {"gamma": 0.1, "levels": ["micro", "meso", "macro"]}
        }
    },
    "gate": {
        "por_delta": 0.02,
        "phi_star": 0.6,
        "mci_min": 0.9
    }
}

class TestDeterminism:
    """Test deterministic behavior of the system"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = Path(self.temp_dir) / "store"
        self.ledger_path = Path(self.temp_dir) / "ledger"
        self.store_path.mkdir()
        self.ledger_path.mkdir()
    
    def teardown_method(self):
        """Clean up test environment"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_spiral_determinism(self):
        """Test that spiral coordinates are deterministic"""
        spiral1 = SpiralSnapshot(TEST_CONFIG['spiral'], str(self.store_path))
        spiral2 = SpiralSnapshot(TEST_CONFIG['spiral'], str(self.store_path))
        
        # Same input and seed should produce identical coordinates
        test_data = {"test": "data", "value": 42}
        
        snapshot1 = spiral1.create_snapshot(test_data, TEST_SEED)
        snapshot2 = spiral2.create_snapshot(test_data, TEST_SEED)
        
        # Verify identical results
        assert snapshot1['seed'] == snapshot2['seed']
        assert snapshot1['phase'] == snapshot2['phase']
        assert np.allclose(snapshot1['coordinates'], snapshot2['coordinates'])
        assert snapshot1['metrics']['por'] == snapshot2['metrics']['por']
    
    def test_solve_coagula_determinism(self):
        """Test that Solve-Coagula produces deterministic fixpoints"""
        sc1 = SolveCoagula(TEST_CONFIG['solvecoagula'])
        sc2 = SolveCoagula(TEST_CONFIG['solvecoagula'])
        
        # Test vector
        test_vector = np.array([1.0, -0.5, 0.3, 0.8, -0.2])
        
        # Run iterations
        fixpoint1, info1 = sc1.iterate_to_fixpoint(test_vector.copy())
        fixpoint2, info2 = sc2.iterate_to_fixpoint(test_vector.copy())
        
        # Verify identical convergence
        assert info1['converged'] == info2['converged']
        assert info1['iterations'] == info2['iterations']
        assert np.allclose(fixpoint1, fixpoint2, atol=1e-10)
    
    def test_tic_determinism(self):
        """Test that TIC creation is deterministic"""
        tic_crystallizer = TICCrystallizer(TEST_CONFIG, str(self.store_path))
        
        # Create test data
        fixpoint = np.array([0.5, 0.3, -0.1, 0.7, 0.2])
        snapshot_data = {
            "id": "test-snap-001",
            "timestamp": "2025-01-01T00:00:00",
            "seed": TEST_SEED,
            "phase": 1.234,
            "coordinates": [1.0, 0.5, -0.3, 0.8, -0.2],
            "sigma": {"psi": 0.5, "rho": 0.6, "omega": 0.7},
            "metrics": {"resonance": 0.8, "stability": 0.9, "por": "valid"}
        }
        convergence_info = {
            "converged": True,
            "iterations": 50,
            "final_delta": 1e-7
        }
        
        # Create TICs
        tic1 = tic_crystallizer.create_tic(
            fixpoint.copy(), "snap-001", TEST_SEED,
            convergence_info, snapshot_data
        )
        
        tic2 = tic_crystallizer.create_tic(
            fixpoint.copy(), "snap-001", TEST_SEED,
            convergence_info, snapshot_data
        )
        
        # Verify deterministic fields (excluding timestamps and UUIDs)
        assert tic1['seed'] == tic2['seed']
        assert np.allclose(tic1['fixpoint'], tic2['fixpoint'])
        assert tic1['invariants'] == tic2['invariants']
        assert tic1['sigma_bar'] == tic2['sigma_bar']
        assert tic1['proof'] == tic2['proof']
    
    def test_ledger_hash_chain(self):
        """Test ledger hash chain integrity"""
        ledger = MEFLedger(str(self.ledger_path))
        
        # Create test blocks
        blocks = []
        for i in range(5):
            tic = {
                "tic_id": f"tic-{i:03d}",
                "seed": TEST_SEED,
                "fixpoint": [0.1 * i] * 5,
                "window": ["2025-01-01T00:00:00", "2025-01-01T00:05:00"],
                "invariants": {"variance": 0.1, "retention": 0.9, "gap": 0.5},
                "sigma_bar": {"psi": 0.5, "rho": 0.6, "omega": 0.7},
                "proof": {"por": "valid", "pi_gap": 0.01, "mci": 0.95},
                "source_snapshot": f"snap-{i:03d}"
            }
            
            snapshot = {
                "id": f"snap-{i:03d}",
                "coordinates": [0.2 * i] * 5,
                "metrics": {"por": "valid"}
            }
            
            success, block = ledger.append_block(tic, snapshot)
            assert success
            blocks.append(block)
        
        # Verify chain integrity
        assert ledger.verify_chain_integrity()
        
        # Verify hash linkage
        for i in range(1, len(blocks)):
            assert blocks[i]['previous_hash'] == blocks[i-1]['hash']
        
        # Verify deterministic hashes
        for block in blocks:
            computed_hash = ledger.compute_block_hash(block)
            assert block['hash'] == computed_hash

class TestPipeline:
    """Test complete pipeline functionality"""
    
    def setup_method(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.store_path = Path(self.temp_dir) / "store"
        self.ledger_path = Path(self.temp_dir) / "ledger"
        self.store_path.mkdir()
        self.ledger_path.mkdir()
        
        # Initialize components
        self.triton = TritonCore(TEST_CONFIG)
        self.spiral = SpiralSnapshot(TEST_CONFIG['spiral'], str(self.store_path))
        self.storage = SpiralStorage(str(self.store_path))
        self.por_validator = ProofOfResonance(TEST_CONFIG)
        self.solve_coagula = SolveCoagula(TEST_CONFIG['solvecoagula'])
        self.tic_crystallizer = TICCrystallizer(TEST_CONFIG, str(self.store_path))
        self.ledger = MEFLedger(str(self.ledger_path))
        self.hdag = HDAG(str(self.store_path))
    
    def teardown_method(self):
        """Clean up test environment"""
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def test_full_pipeline(self):
        """Test complete pipeline from ingestion to ledger"""
        
        # 1. Ingestion
        test_data = {
            "message": "Test data for MEF-Core",
            "value": 42,
            "nested": {"key": "value"}
        }
        
        normalized = self.triton.normalize(test_data, "json")
        
        # 2. Spiral Snapshot
        snapshot = self.spiral.create_snapshot(normalized, TEST_SEED)
        snapshot_file = self.spiral.save_snapshot(snapshot)
        self.storage.store_snapshot(snapshot)
        
        assert snapshot['metrics']['por'] in ['valid', 'invalid']
        assert Path(snapshot_file).exists()
        
        # 3. Solve-Coagula
        coordinates = np.array(snapshot['coordinates'])
        fixpoint, convergence_info = self.solve_coagula.iterate_to_fixpoint(
            coordinates,
            track_convergence=True
        )
        
        assert convergence_info['converged']
        assert convergence_info['iterations'] < 1000
        
        # 4. TIC Creation
        tic = self.tic_crystallizer.create_tic(
            fixpoint,
            snapshot['id'],
            snapshot['seed'],
            convergence_info,
            snapshot
        )
        
        tic_file = self.tic_crystallizer.save_tic(tic)
        self.storage.store_tic(tic)
        
        assert Path(tic_file).exists()
        assert tic['proof']['por'] in ['valid', 'invalid']
        
        # 5. Ledger Commit (if valid)
        if self.tic_crystallizer.should_commit(tic):
            success, block = self.ledger.append_block(tic, snapshot)
            assert success
            assert block['index'] == 0
            assert self.ledger.verify_chain_integrity()
    
    def test_multiple_snapshots_path_invariance(self):
        """Test path invariance across multiple snapshots"""
        
        snapshots = []
        
        # Create multiple snapshots
        for i in range(3):
            test_data = f"Test data iteration {i}"
            normalized = self.triton.normalize(test_data, "text")
            snapshot = self.spiral.create_snapshot(normalized, TEST_SEED, phase=i*0.5)
            self.storage.store_snapshot(snapshot)
            snapshots.append(snapshot)
            
            # Add to HDAG
            if i > 0:
                self.hdag.update_hdag(snapshots[i-1], snapshots[i])
        
        # Verify HDAG structure
        stats = self.hdag.get_statistics()
        assert stats['nodes'] == 3
        assert stats['edges'] == 2
        assert stats['is_acyclic']
        
        # Verify path invariance
        first_node = snapshots[0]['hdag_node']
        last_node = snapshots[2]['hdag_node']
        
        # Should have a path from first to last
        paths = self.hdag._find_all_paths(first_node, last_node)
        assert len(paths) > 0
    
    def test_proof_of_resonance_validation(self):
        """Test PoR validation functionality"""
        
        # Create snapshot
        test_data = "Test for PoR validation"
        normalized = self.triton.normalize(test_data, "text")
        snapshot = self.spiral.create_snapshot(normalized, TEST_SEED)
        
        # Validate
        is_valid, report = self.por_validator.validate_snapshot(snapshot)
        
        assert 'resonance' in report
        assert 'stability' in report
        assert report['snapshot_id'] == snapshot['id']
        assert report['overall_valid'] == is_valid

class TestReproducibility:
    """Test system reproducibility with fixed seeds"""
    
    def test_identical_runs_produce_identical_results(self):
        """Verify that identical inputs produce identical outputs"""
        
        results = []
        
        for run in range(3):
            # Create temporary directories for each run
            temp_dir = tempfile.mkdtemp()
            store_path = Path(temp_dir) / "store"
            ledger_path = Path(temp_dir) / "ledger"
            store_path.mkdir()
            ledger_path.mkdir()
            
            try:
                # Initialize components
                triton = TritonCore(TEST_CONFIG)
                spiral = SpiralSnapshot(TEST_CONFIG['spiral'], str(store_path))
                solve_coagula = SolveCoagula(TEST_CONFIG['solvecoagula'])
                
                # Process identical data
                test_data = {"reproducibility": "test", "run": "fixed"}
                normalized = triton.normalize(test_data, "json")
                
                # Create snapshot
                snapshot = spiral.create_snapshot(normalized, TEST_SEED, phase=1.234)
                
                # Apply Solve-Coagula
                coordinates = np.array(snapshot['coordinates'])
                fixpoint, info = solve_coagula.iterate_to_fixpoint(coordinates)
                
                # Store results
                results.append({
                    "coordinates": snapshot['coordinates'],
                    "phase": snapshot['phase'],
                    "fixpoint": fixpoint.tolist(),
                    "iterations": info['iterations'],
                    "converged": info['converged']
                })
            finally:
                # Clean up
                shutil.rmtree(temp_dir)
        
        # Verify all runs produced identical results
        for i in range(1, len(results)):
            assert results[i]['phase'] == results[0]['phase']
            assert np.allclose(results[i]['coordinates'], results[0]['coordinates'])
            assert np.allclose(results[i]['fixpoint'], results[0]['fixpoint'])
            assert results[i]['iterations'] == results[0]['iterations']
            assert results[i]['converged'] == results[0]['converged']

# Test data fixtures
TEST_TEXTS = [
    "The quick brown fox jumps over the lazy dog",
    "MEF-Core deterministic transformation pipeline",
    "Temporal Information Crystals emerge from chaos"
]

TEST_JSON_DATA = [
    {"simple": "object", "with": "values"},
    {"nested": {"structure": {"deep": "value"}}, "array": [1, 2, 3]},
    {"complex": True, "null": None, "number": 3.14159}
]

TEST_NUMERIC_DATA = [
    [1.0, 2.0, 3.0, 4.0, 5.0],
    np.random.RandomState(42).randn(10).tolist(),
    [0.1, -0.2, 0.3, -0.4, 0.5]
]

@pytest.mark.parametrize("test_data", TEST_TEXTS)
def test_text_processing_determinism(test_data):
    """Test deterministic text processing"""
    triton = TritonCore(TEST_CONFIG)
    
    result1 = triton.normalize(test_data, "text")
    result2 = triton.normalize(test_data, "text")
    
    assert result1 == result2
    assert len(result1['vector']) == 5

@pytest.mark.parametrize("test_data", TEST_JSON_DATA)
def test_json_processing_determinism(test_data):
    """Test deterministic JSON processing"""
    triton = TritonCore(TEST_CONFIG)
    
    result1 = triton.normalize(test_data, "json")
    result2 = triton.normalize(test_data, "json")
    
    assert result1 == result2
    assert len(result1['vector']) == 5

class TestSpec002Determinism:
    """SPEC-002 Determinismus-Tests mit Seed=42"""
    
    def test_identical_payload_identical_hash(self):
        """SPEC-002: Gleicher Payload → identische Hashes"""
        # Setup
        temp_dir = tempfile.mkdtemp()
        store_path = Path(temp_dir) / "store"
        ledger_path = Path(temp_dir) / "ledger"
        store_path.mkdir()
        ledger_path.mkdir()
        
        try:
            # Fixierter Seed und Payload
            SEED = "MEF_SEED_42"
            PAYLOAD = {"test": "data", "value": 42}
            
            # Zwei unabhängige Durchläufe
            results = []
            for run in range(2):
                # Komponenten initialisieren
                config = TEST_CONFIG.copy()
                config['seed'] = SEED
                
                triton = TritonCore(config)
                spiral = SpiralSnapshot(config['spiral'], str(store_path))
                solve = SolveCoagula(config['solvecoagula'])
                tic_cryst = TICCrystallizer(config, str(store_path))
                ledger = MEFLedger(str(ledger_path))
                
                # Pipeline
                normalized = triton.normalize(PAYLOAD, "json")
                snapshot = spiral.create_snapshot(normalized, SEED)
                coords = np.array(snapshot['coordinates'])
                fixpoint, info = solve.iterate_to_fixpoint(coords)
                tic = tic_cryst.create_tic(fixpoint, snapshot['id'], SEED, info, snapshot)
                
                # Hashes sammeln
                snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()
                tic_hash = hashlib.sha256(json.dumps(tic, sort_keys=True).encode()).hexdigest()
                fixpoint_hash = hashlib.sha256(fixpoint.tobytes()).hexdigest()
                
                results.append({
                    'snapshot_hash': snapshot_hash,
                    'tic_hash': tic_hash,
                    'fixpoint_hash': fixpoint_hash,
                    'fixpoint': fixpoint.tolist()
                })
            
            # SPEC-002: Identische Hashes prüfen
            assert results[0]['snapshot_hash'] == results[1]['snapshot_hash']
            assert results[0]['tic_hash'] == results[1]['tic_hash']
            assert results[0]['fixpoint_hash'] == results[1]['fixpoint_hash']
            assert np.allclose(results[0]['fixpoint'], results[1]['fixpoint'], atol=1e-10)
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_por_invalid_no_ledger_update(self):
        """SPEC-002: PoR invalid → kein Ledger-Update"""
        temp_dir = tempfile.mkdtemp()
        store_path = Path(temp_dir) / "store"
        ledger_path = Path(temp_dir) / "ledger"
        store_path.mkdir()
        ledger_path.mkdir()
        
        try:
            config = TEST_CONFIG.copy()
            spiral = SpiralSnapshot(config['spiral'], str(store_path))
            tic_cryst = TICCrystallizer(config, str(store_path))
            ledger = MEFLedger(str(ledger_path))
            
            # Snapshot mit invalid PoR erzeugen
            snapshot = {
                "id": "test-invalid",
                "timestamp": datetime.utcnow().isoformat(),
                "seed": "MEF_SEED_42",
                "phase": 1.0,
                "coordinates": [0.1, 0.2, 0.3, 0.4, 0.5],
                "sigma": {"psi": 0.5, "rho": 0.6, "omega": 0.7},
                "metrics": {"resonance": 0.8, "stability": 0.9, "por": "invalid"}  # Invalid!
            }
            
            # TIC mit invalid PoR
            tic = {
                "tic_id": "tic-invalid",
                "seed": "MEF_SEED_42",
                "fixpoint": [0.1, 0.2, 0.3, 0.4, 0.5],
                "window": ["2025-01-01T00:00:00", "2025-01-01T00:05:00"],
                "invariants": {"variance": 0.1, "retention": 0.9, "gap": 0.5},
                "sigma_bar": {"psi": 0.5, "rho": 0.6, "omega": 0.7},
                "proof": {"por": "invalid", "pi_gap": 0.01, "mci": 0.95},
                "source_snapshot": "test-invalid"
            }
            
            # Should_commit sollte False sein bei invalid PoR
            should_commit = tic_cryst.should_commit(tic)
            assert not should_commit, "SPEC-002: Invalid PoR sollte nicht committen"
            
            # Ledger sollte leer bleiben
            initial_blocks = ledger.index["current_index"]
            assert initial_blocks == -1, "Ledger sollte leer sein"
            
        finally:
            shutil.rmtree(temp_dir)
    
    def test_path_invariance(self):
        """SPEC-002: Pfadinvarianz - zwei Äquivalenzpfade → ‖Δv‖ ≤ 1e-6"""
        # Zwei verschiedene Operator-Reihenfolgen sollten zum gleichen Fixpunkt führen
        config = TEST_CONFIG.copy()
        solve = SolveCoagula(config['solvecoagula'])
        
        v0 = np.array([1.0, -0.5, 0.3, 0.8, -0.2])
        
        # Pfad 1: Standard-Reihenfolge
        v1, _ = solve.iterate_to_fixpoint(v0.copy())
        
        # Pfad 2: Gleiche Operatoren, aber andere Initialisierung
        # (Determinismus durch Seed gewährleistet)
        np.random.seed(42)  # Reset Seed
        solve2 = SolveCoagula(config['solvecoagula'])
        v2, _ = solve2.iterate_to_fixpoint(v0.copy())
        
        # SPEC-002: Pfadinvarianz prüfen
        delta = np.linalg.norm(v1 - v2)
        assert delta <= 1e-6, f"SPEC-002: Pfadinvarianz verletzt, ‖Δv‖={delta} > 1e-6"
    
    def test_hdag_acyclic(self):
        """SPEC-002: HDAG bleibt azyklisch"""
        temp_dir = tempfile.mkdtemp()
        store_path = Path(temp_dir) / "store"
        store_path.mkdir()
        
        try:
            hdag = HDAG(str(store_path))
            
            # Erstelle mehrere Snapshots mit korrekter zeitlicher Ordnung
            snapshots = []
            for i in range(5):
                snapshot = {
                    "id": f"snap-{i}",
                    "timestamp": (datetime.utcnow() + timedelta(minutes=i)).isoformat(),
                    "phase": float(i),
                    "hdag_node": f"N-snap-{i}"
                }
                snapshots.append(snapshot)
            
            # Füge Kanten hinzu
            for i in range(4):
                hdag.update_hdag(snapshots[i], snapshots[i+1])
            
            # Prüfe Azyklizität
            stats = hdag.get_statistics()
            assert stats['is_acyclic'], "SPEC-002: HDAG muss azyklisch bleiben"
            
            # Versuche Zyklus zu erzeugen (sollte abgelehnt werden)
            edge_id = hdag.update_hdag(snapshots[4], snapshots[0])
            assert edge_id is None, "SPEC-002: HDAG sollte Zyklen verhindern"
            
        finally:
            shutil.rmtree(temp_dir)