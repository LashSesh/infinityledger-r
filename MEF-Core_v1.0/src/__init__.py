# src/__init__.py
__version__ = "1.0.0"
__author__ = "MEF-Core Project"
__license__ = "MIT"

from .spiral.snapshot import SpiralSnapshot
from .spiral.storage import SpiralStorage
from .spiral.proof_of_resonance import ProofOfResonance
from .solvecoagula.operators import SolveCoagula
from .tic.crystallizer import TICCrystallizer
from .ledger.mef_block import MEFLedger
from .hdag.graph import HDAG
from .ingestion.triton_core import TritonCore
from .audit.logger import MEFAuditLogger

__all__ = [
    "SpiralSnapshot",
    "SpiralStorage", 
    "ProofOfResonance",
    "SolveCoagula",
    "TICCrystallizer",
    "MEFLedger",
    "HDAG",
    "TritonCore",
    "MEFAuditLogger",
]

class MEFCore:
    """
    Main MEF-Core interface for simplified usage.
    """
    
    def __init__(self, seed: str = "MEF_SEED_42", config: dict = None):
        """
        Initialize MEF-Core with seed and optional configuration.
        
        Args:
            seed: Deterministic seed
            config: Optional configuration dictionary
        """
        self.seed = seed
        
        if config is None:
            config = {
                "seed": seed,
                "spiral": {
                    "r": 1.0, "a": 0.05, "b": 0.2, "c": 0.2, "k": 2, "step": 0.01
                },
                "solvecoagula": {
                    "lambda": 0.8, "eps": 1e-6, "max_iter": 1000,
                    "operators": {
                        "dk": {"alpha1": 0.05, "alpha2": -0.03},
                        "sw": {"tau0": 0.5, "beta": 0.1, "schedule": "cosine"},
                        "pi": {"canon": "lexicographic", "tol": 1e-6},
                        "wt": {"gamma": 0.1, "levels": ["micro", "meso", "macro"]}
                    }
                },
                "gate": {
                    "por_delta": 0.02, "phi_star": 0.6, "mci_min": 0.9
                }
            }
        
        self.config = config
        
        # Initialize components
        self.triton = TritonCore(config)
        self.spiral = SpiralSnapshot(config['spiral'])
        self.storage = SpiralStorage()
        self.por_validator = ProofOfResonance(config)
        self.solve_coagula = SolveCoagula(config['solvecoagula'])
        self.tic_crystallizer = TICCrystallizer(config)
        self.ledger = MEFLedger()
        self.hdag = HDAG()
        self.logger = MEFAuditLogger()
    
    def process(self, data: any, data_type: str = "raw", auto_commit: bool = True) -> dict:
        """
        Process data through complete MEF-Core pipeline.
        
        Args:
            data: Input data
            data_type: Type of data (text, json, numeric, binary, raw)
            auto_commit: Whether to auto-commit to ledger
            
        Returns:
            Processing results dictionary
        """
        # 1. Normalize through Triton
        normalized = self.triton.normalize(data, data_type)
        
        # 2. Create Spiral snapshot
        snapshot = self.spiral.create_snapshot(normalized, self.seed)
        snapshot_file = self.spiral.save_snapshot(snapshot)
        self.storage.store_snapshot(snapshot)
        
        # Log snapshot creation
        self.logger.log_snapshot_creation(snapshot)
        
        # 3. Apply Solve-Coagula
        import numpy as np
        coordinates = np.array(snapshot['coordinates'])
        fixpoint, convergence_info = self.solve_coagula.iterate_to_fixpoint(
            coordinates, track_convergence=True
        )
        
        # 4. Create TIC
        tic = self.tic_crystallizer.create_tic(
            fixpoint, snapshot['id'], snapshot['seed'],
            convergence_info, snapshot
        )
        self.tic_crystallizer.save_tic(tic)
        self.storage.store_tic(tic)
        
        # Log TIC generation
        self.logger.log_tic_generation(tic, convergence_info)
        
        # 5. Commit to ledger if valid
        block = None
        committed = False
        if auto_commit and self.tic_crystallizer.should_commit(tic):
            success, result = self.ledger.append_block(tic, snapshot)
            if success:
                block = result
                committed = True
                
                # Log ledger commit
                self.logger.log_ledger_commit(block)
        
        return {
            "snapshot_id": snapshot['id'],
            "snapshot_phase": snapshot['phase'],
            "por": snapshot['metrics']['por'],
            "tic_id": tic['tic_id'],
            "converged": convergence_info['converged'],
            "iterations": convergence_info['iterations'],
            "committed": committed,
            "block_index": block['index'] if block else None,
            "block_hash": block['hash'] if block else None
        }