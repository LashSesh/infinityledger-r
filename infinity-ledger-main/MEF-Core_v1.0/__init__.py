"""Lightweight facade for the MEF-Core components."""

from __future__ import annotations

from importlib import import_module
from typing import Any, Dict

__all__ = ["MEFCore", "load_component"]

_COMPONENT_MAP = {
    "SpiralSnapshot": "src.spiral.snapshot.SpiralSnapshot",
    "SpiralStorage": "src.spiral.storage.SpiralStorage",
    "ProofOfResonance": "src.spiral.proof_of_resonance.ProofOfResonance",
    "SolveCoagula": "src.solvecoagula.operators.SolveCoagula",
    "TICCrystallizer": "src.tic.crystallizer.TICCrystallizer",
    "MEFLedger": "src.ledger.mef_block.MEFLedger",
    "HDAG": "src.hdag.graph.HDAG",
    "TritonCore": "src.ingestion.triton_core.TritonCore",
    "MEFAuditLogger": "src.audit.logger.MEFAuditLogger",
}


def load_component(name: str):
    """Resolve a high-level component by name."""

    target = _COMPONENT_MAP.get(name)
    if not target:
        raise KeyError(f"Unknown component: {name}")
    module_name, attr = target.rsplit(".", 1)
    module = import_module(module_name)
    return getattr(module, attr)


class MEFCore:
    """Convenience wrapper that wires together the main MEF-Core services."""

    def __init__(self, seed: str = "MEF_SEED_42", config: Dict[str, Any] | None = None):
        self.seed = seed
        self.config = config or {
            "seed": seed,
            "spiral": {"r": 1.0, "a": 0.05, "b": 0.2, "c": 0.2, "k": 2, "step": 0.01},
            "solvecoagula": {
                "lambda": 0.8,
                "eps": 1e-6,
                "max_iter": 1000,
                "operators": {
                    "dk": {"alpha1": 0.05, "alpha2": -0.03},
                    "sw": {"tau0": 0.5, "beta": 0.1, "schedule": "cosine"},
                    "pi": {"canon": "lexicographic", "tol": 1e-6},
                    "wt": {"gamma": 0.1, "levels": ["micro", "meso", "macro"]},
                },
            },
            "gate": {"por_delta": 0.02, "phi_star": 0.6, "mci_min": 0.9},
        }

        self.triton = load_component("TritonCore")(self.config)
        self.spiral = load_component("SpiralSnapshot")(self.config["spiral"])
        self.storage = load_component("SpiralStorage")()
        self.por_validator = load_component("ProofOfResonance")(self.config)
        self.solve_coagula = load_component("SolveCoagula")(self.config["solvecoagula"])
        self.tic_crystallizer = load_component("TICCrystallizer")(self.config)
        self.ledger = load_component("MEFLedger")()
        self.hdag = load_component("HDAG")()
        self.logger = load_component("MEFAuditLogger")()

    def process(self, data: Any, data_type: str = "raw", auto_commit: bool = True) -> Dict[str, Any]:
        """Execute the full deterministic processing pipeline for the given payload."""

        normalized = self.triton.normalize(data, data_type)
        snapshot = self.spiral.create_snapshot(normalized, self.seed)
        self.storage.store_snapshot(snapshot)
        self.logger.log_snapshot_creation(snapshot)

        import numpy as np

        coordinates = np.array(snapshot["coordinates"])
        fixpoint, convergence = self.solve_coagula.iterate_to_fixpoint(coordinates, track_convergence=True)

        tic = self.tic_crystallizer.create_tic(
            fixpoint, snapshot["id"], snapshot["seed"], convergence, snapshot
        )
        self.tic_crystallizer.save_tic(tic)
        self.storage.store_tic(tic)
        self.logger.log_tic_generation(tic, convergence)

        committed = False
        block = None
        if auto_commit and self.tic_crystallizer.should_commit(tic):
            success, result = self.ledger.append_block(tic, snapshot)
            if success:
                block = result
                committed = True
                self.logger.log_ledger_commit(block)

        return {
            "snapshot_id": snapshot["id"],
            "snapshot_phase": snapshot["phase"],
            "por": snapshot["metrics"]["por"],
            "tic_id": tic["tic_id"],
            "converged": convergence["converged"],
            "iterations": convergence["iterations"],
            "committed": committed,
            "block_index": block["index"] if block else None,
            "block_hash": block["hash"] if block else None,
        }
