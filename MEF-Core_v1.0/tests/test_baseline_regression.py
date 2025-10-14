"""Non-regression checks against the recorded baseline artefacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List
import sys
import math
import subprocess

import copy

import pytest
import yaml

MEF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEF_ROOT / "src"))

from ingestion.triton_core import TritonCore
from spiral.snapshot import SpiralSnapshot
from spiral.proof_of_resonance import ProofOfResonance
from vector_db.index_manager import IndexManager, VectorRecord
from api.grpc.vector_server import _cosine_similarity
from api import server as api_server

REPO_ROOT = MEF_ROOT.parent
BASELINE_PATH = REPO_ROOT / "baseline.json"
CONFIG_PATH = MEF_ROOT / "config.yaml"


@pytest.fixture(scope="module")
def baseline() -> Dict[str, object]:
    data = json.loads(BASELINE_PATH.read_text())
    return copy.deepcopy(data)


@pytest.fixture(scope="module")
def config() -> Dict[str, object]:
    return copy.deepcopy(yaml.safe_load(CONFIG_PATH.read_text()))


def _hash_json(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def test_baseline_tag_matches_commit(baseline: Dict[str, object]):
    try:
        tag_commit = subprocess.check_output([
            "git", "rev-parse", "v0-baseline"
        ], stderr=subprocess.STDOUT).decode().strip()
    except subprocess.CalledProcessError:
        commit_check = subprocess.run(
            ["git", "cat-file", "-t", baseline["git_commit"]],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if commit_check.returncode != 0:
            pytest.skip("baseline commit not present in repository")
        subprocess.check_call(["git", "tag", "v0-baseline", baseline["git_commit"]])
        tag_commit = baseline["git_commit"]
    assert baseline["git_commit"] == tag_commit


def test_embedding_vector_matches_baseline(baseline: Dict[str, object], config: Dict[str, object]):
    triton = TritonCore(config)
    sample_payload = baseline["embedding_version"]["sample_payload"]  # type: ignore[index]
    normalized = triton.normalize(sample_payload, "json")
    vector: List[float] = normalized["vector"]

    expected_vector = baseline["embedding_version"]["vector"]  # type: ignore[index]
    assert len(vector) == len(expected_vector)
    for actual, expected in zip(vector, expected_vector):
        assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-12)

    vector_hash = _hash_json(vector)
    assert vector_hash == baseline["embedding_version"]["vector_hash"]  # type: ignore[index]


def test_vector_search_regression(baseline: Dict[str, object], config: Dict[str, object], tmp_path: Path):
    baseline_vector = baseline["embedding_version"]["vector"]  # type: ignore[index]

    manager = IndexManager(tmp_path)
    records = [
        VectorRecord(id="baseline-anchor", values=baseline_vector, metadata={"role": "anchor"}, epoch=1),
        VectorRecord(id="baseline-neighbor", values=[v * 0.98 for v in baseline_vector], metadata={"role": "neighbor"}, epoch=1),
        VectorRecord(id="baseline-inverse", values=[-v for v in baseline_vector], metadata={"role": "inverse"}, epoch=1),
    ]
    manager.upsert_vectors("baseline", records, epoch=1)

    state = manager.get_collection_state("baseline")
    scored = []
    for vector_id, payload in state.vectors.items():
        score = _cosine_similarity(baseline_vector, payload["vector"])
        scored.append({
            "id": vector_id,
            "score": round(score, 10),
            "epoch": payload["epoch"],
        })

    scored.sort(key=lambda item: item["score"], reverse=True)
    top_results = scored[:3]

    assert top_results == baseline["non_regression"]["vector_search"]["results"]  # type: ignore[index]
    assert _hash_json(top_results) == baseline["non_regression"]["vector_search"]["result_hash"]  # type: ignore[index]


def test_proof_of_resonance_regression(baseline: Dict[str, object], config: Dict[str, object], tmp_path: Path):
    triton = TritonCore(config)
    sample_payload = baseline["embedding_version"]["sample_payload"]  # type: ignore[index]
    normalized = triton.normalize(sample_payload, "json")

    spiral = SpiralSnapshot(config["spiral"], str(tmp_path / "store"))
    snapshot = spiral.create_snapshot(normalized, config["seed"])
    assert snapshot["id"] == baseline["non_regression"]["proof_of_resonance"]["snapshot_id"]  # type: ignore[index]

    por = ProofOfResonance(config)
    is_valid, report = por.validate_snapshot(snapshot)
    proof_data = {
        "snapshot_id": snapshot["id"],
        "coordinates": snapshot["coordinates"],
        "resonance": report["resonance"]["fft_resonance"],
        "spectral_gap": report["resonance"]["spectral_gap"],
        "stability": report["stability"]["computed"],
        "valid": is_valid,
    }
    manual_hash = _hash_json(proof_data)

    proof_hash = por.generate_por_proof(snapshot)

    assert proof_hash == manual_hash
    assert manual_hash == baseline["non_regression"]["proof_of_resonance"]["proof_hash"]  # type: ignore[index]
    assert snapshot["metrics"]["por"] == baseline["non_regression"]["proof_of_resonance"]["por_status"]  # type: ignore[index]


def test_openapi_schema_hash_matches_baseline(baseline: Dict[str, object]):
    openapi_schema = api_server.app.openapi()
    assert _hash_json(openapi_schema) == baseline["api_hash"]["openapi_sha256"]  # type: ignore[index]
    assert len(openapi_schema.get("paths", {})) == baseline["api_hash"]["endpoints"]  # type: ignore[index]
