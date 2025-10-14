import json
from pathlib import Path

import numpy as np

# Provide lightweight SciPy stubs required by the domain layer during import
import sys
import types

if "scipy" not in sys.modules:
    scipy_module = types.ModuleType("scipy")
    spatial_module = types.ModuleType("scipy.spatial")

    class _Delaunay:  # pragma: no cover - simple placeholder
        def __init__(self, points):
            self.points = np.asarray(points)

        def find_simplex(self, _):
            return np.zeros(len(self.points))

    spatial_module.Delaunay = _Delaunay
    stats_module = types.ModuleType("scipy.stats")

    def _entropy(values):
        values = np.asarray(values, dtype=float)
        probs = np.abs(values) / (np.sum(np.abs(values)) + 1e-12)
        with np.errstate(divide="ignore", invalid="ignore"):
            log_probs = np.log(probs + 1e-12)
        return float(-np.sum(probs * log_probs))

    stats_module.entropy = _entropy

    scipy_module.spatial = spatial_module
    scipy_module.stats = stats_module

    sys.modules["scipy"] = scipy_module
    sys.modules["scipy.spatial"] = spatial_module
    sys.modules["scipy.stats"] = stats_module

if "sklearn" not in sys.modules:
    sklearn_module = types.ModuleType("sklearn")
    decomposition_module = types.ModuleType("sklearn.decomposition")

    class _PCA:  # pragma: no cover - placeholder PCA implementation
        def __init__(self, n_components=None):
            self.n_components = n_components

        def fit_transform(self, values):
            values = np.asarray(values, dtype=float)
            if self.n_components is None or self.n_components >= values.shape[1]:
                return values
            return values[:, : self.n_components]

    decomposition_module.PCA = _PCA
    sklearn_module.decomposition = decomposition_module

    sys.modules["sklearn"] = sklearn_module
    sys.modules["sklearn.decomposition"] = decomposition_module

if "src.api" not in sys.modules:
    api_module = types.ModuleType("src.api")

    def _export_stub(*_args, **_kwargs):  # pragma: no cover - placeholder
        return {}

    api_module.export_nodes_json = _export_stub
    api_module.export_edges_json = _export_stub
    api_module.export_adjacency_json = _export_stub
    api_module.export_group_json = _export_stub
    api_module.export_matrices_json = _export_stub

    sys.modules["src.api"] = api_module

from src.domains.domain_layer import DomainLayer
from src.domains.xswap import Xswap
from src.gates.merkaba_gate import MerkabaGate
from src.hdag.graph import HDAG
from src.ledger.mef_block import MEFLedger
from src.mef_core_pipeline import MEFCorePipeline


def test_xswap_alignment_commits_ledger(tmp_path):
    np.random.seed(42)

    storage_path = tmp_path / "store"
    ledger_path = tmp_path / "ledger"
    domain_storage = tmp_path / "domains"
    audit_path = tmp_path / "audit" / "xswap.jsonl"

    pipeline = MEFCorePipeline(
        seed="TEST_XSWAP",
        storage_path=str(storage_path),
        ledger_path=str(ledger_path),
        metatron_cache=False,
    )

    domain_layer = DomainLayer(
        mef_pipeline=pipeline,
        metatron_router=pipeline.metatron_router,
        storage_path=str(domain_storage),
    )

    merkaba = MerkabaGate(epsilon=1.0, phi_star=0.1, eta=0.1)
    hdag = HDAG(str(tmp_path / "hdag"))
    ledger = MEFLedger(str(ledger_path))

    xswap = Xswap(
        domain_layer=domain_layer,
        merkaba_gate=merkaba,
        hdag=hdag,
        ledger=ledger,
        audit_path=audit_path,
    )

    source_text = "The Merkaba alignment initiates coherent resonance between domains."
    target_signal = [0.3, 0.8, 0.6, 0.2, 0.4, 0.9, 0.5]

    artifacts = xswap.align(
        source_payload=source_text,
        target_payload=target_signal,
        source_domain="text",
        target_domain="signal",
        merkaba_thresholds={"epsilon": 1.0, "phi_star": 0.05, "eta": 0.05},
    )

    assert 0.0 <= artifacts.alignment_score <= 1.0
    assert artifacts.gate_event["decision"]["commit"] is True
    assert artifacts.ledger_block is not None
    assert artifacts.hdag_data["path"].get("invariant") in {True, False}

    audit_file = Path(audit_path)
    assert audit_file.exists()

    with audit_file.open("r", encoding="utf-8") as handle:
        entries = [json.loads(line) for line in handle]

    assert entries[-1]["alignment_id"] == artifacts.alignment_id
    assert entries[-1]["gate_event"]["decision"]["commit"] is True
