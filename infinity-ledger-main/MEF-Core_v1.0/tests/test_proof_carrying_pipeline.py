from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Dict, List

import pytest
from fastapi.testclient import TestClient

MEF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEF_ROOT / "src"))

from api import server as api_server
from vector_db.index_manager import VectorRecord


def _header() -> Dict[str, str]:
    return {"Authorization": f"Bearer {api_server.API_TOKEN}"}


@pytest.fixture()
def client():
    with TestClient(api_server.app) as client:
        yield client


def _seed_vectors() -> List[VectorRecord]:
    base = [0.1, 0.2, 0.3, 0.4]
    records = []
    for idx in range(4):
        vec = [value + idx * 0.01 for value in base]
        records.append(
            VectorRecord(
                id=f"vec-{idx}",
                values=vec,
                metadata={"bucket": idx},
                epoch=1,
            )
        )
    api_server.index_manager.collections.clear()
    api_server.index_manager.collection_providers.clear()
    api_server.index_manager._provider_instances.clear()  # type: ignore[attr-defined]
    api_server.index_manager.upsert_vectors("proof", records, epoch=1)
    api_server.proof_registry.refresh_from_collections(api_server.index_manager.collections)
    return records


def _hash_pipeline(payload: Dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def test_proof_carrying_retrieval(client):
    records = _seed_vectors()
    query_vector = list(records[0].values)

    response = client.post(
        "/search",
        headers=_header(),
        json={
            "collection": "proof",
            "query_vector": query_vector,
            "top_k": 3,
            "membership_proof": True,
            "pipeline_proof": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()

    commit = payload["commit"]
    assert commit["kid"] == api_server.proof_registry.kid
    assert commit["commit_root"] == api_server.proof_registry.commit_root

    result = payload["results"][0]
    membership = result["membership_proof"]
    assert membership["collection"] == "proof"

    proof = api_server.proof_registry.get_membership_proof("proof", result["id"])
    assert proof is not None
    assert proof.verify(commit_root=commit["commit_root"]) is True

    pipeline_payload = {
        "collection": "proof",
        "query": query_vector,
        "top_k": 3,
        "provider": api_server.index_manager.collection_providers.get("proof"),
        "commit_root": commit["commit_root"],
        "result_id": result["id"],
    }
    assert result["pipeline_proof"] == _hash_pipeline(pipeline_payload)

    commit_response = client.get("/commit", headers=_header())
    assert commit_response.status_code == 200
    assert commit_response.json() == commit

    proof_identifier = f"proof:{result['id']}"
    proof_response = client.get(f"/proof/{proof_identifier}", headers=_header())
    assert proof_response.status_code == 200
    proof_payload = proof_response.json()
    assert proof_payload["leaf"] == membership["leaf"]

    batch_response = client.post(
        "/proof/batch",
        headers=_header(),
        json={"members": [{"collection": "proof", "vector_id": result["id"]}]},
    )
    assert batch_response.status_code == 200
    batch_payload = batch_response.json()
    assert batch_payload["commit"]["commit_root"] == commit["commit_root"]
    assert batch_payload["proofs"][0]["vector_id"] == result["id"]


def test_scorpio_tick_determinism(client):
    _seed_vectors()
    first_mode = client.get("/mode", headers=_header())
    assert first_mode.status_code == 200
    snapshot_a = first_mode.json()

    api_server.scorpio_sync.advance(active={"probe": "a"})
    second_mode = client.get("/mode", headers=_header())
    assert second_mode.status_code == 200
    snapshot_b = second_mode.json()

    assert snapshot_b["tick_no"] == snapshot_a["tick_no"] + 1
    assert snapshot_b["seed"] == snapshot_a["seed"]
    assert snapshot_b["tick_proof"] != snapshot_a["tick_proof"]


def test_delta_pi_enforcer_triggers_422(monkeypatch, client):
    headers = _header()
    acquisition = client.post(
        "/acquisition",
        json={"asset": "delta-pi", "timestamp": "2025-01-01", "metrics": {"alpha": 0.1}},
    )
    snapshot_id = acquisition.json()["snapshot_id"]
    snapshot = api_server.storage.retrieve_snapshot(snapshot_id)
    snapshot["metrics"]["por"] = "valid"
    api_server.storage.store_snapshot(snapshot)

    original_create = api_server.tic_crystallizer.create_tic

    def _patched_create_tic(*args, **kwargs):
        tic = original_create(*args, **kwargs)
        tic["invariants"]["delta_pi"] = api_server.EPS_PI_DEFAULT * 10
        return tic

    monkeypatch.setattr(api_server.tic_crystallizer, "create_tic", _patched_create_tic)

    response = client.post("/solve", params={"snapshot_id": snapshot_id}, headers=headers)
    assert response.status_code == 422
    stats = client.get("/stats", headers=headers).json()
    assert stats["delta_pi_violations"] >= 1


def test_index_provider_switch_and_metrics(client):
    _seed_vectors()
    providers = client.get("/index/providers", headers=_header())
    assert providers.status_code == 200
    payload = providers.json()
    assert "ivf_pq" in payload

    update = client.patch(
        "/collections/proof/provider",
        headers=_header(),
        json={"provider": "ivf_pq"},
    )
    assert update.status_code == 200
    update_payload = update.json()
    assert update_payload["provider"] == "ivf_pq"
    assert update_payload.get("ready") is False
    assert "proof_version" in update_payload

    search = client.post(
        "/search",
        headers=_header(),
        json={
            "collection": "proof",
            "query_vector": list(api_server.index_manager.get_collection_state("proof").vectors["vec-0"]["vector"]),
            "top_k": 1,
        },
    )
    assert search.status_code == 200
    stats = client.get("/stats", headers=_header()).json()
    assert "search" in stats["metrics"]
