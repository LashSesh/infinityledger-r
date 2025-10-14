"""Proof verification across provider overrides."""

from __future__ import annotations

from typing import Dict, Optional

import pytest

from ..quality_utils import load_golden_dataset, request_json, request_raw, skip_unless_service_available, sort_hits
from .pipeline_helpers import SolveHoldDueToPOR, run_roundtrip

sys_path_added = False

if not sys_path_added:
    import sys
    from pathlib import Path

    MEF_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(MEF_ROOT))
    sys_path_added = True

from tools.recompute_pipeline import recompute_pipeline_proof
from tools.verify_membership import verify_hits

ALT_PROVIDER = "ivf_pq"


def _roundtrip_sample() -> Optional[Dict[str, object]]:
    dataset = load_golden_dataset()
    for sample in dataset:
        try:
            return run_roundtrip(sample, membership_proof=True, pipeline_proof=True)
        except SolveHoldDueToPOR:
            continue
    return None


@pytest.mark.property
def test_read_only_provider_override_preserves_proofs() -> None:
    skip_unless_service_available()

    roundtrip = _roundtrip_sample()
    if roundtrip is None:
        pytest.skip("No dataset entries produced verifiable proofs due to PoR holds")

    collection = roundtrip.collection
    status_before = request_json("GET", f"/index/status?collection={collection}")
    proof_version_before = int(status_before.get("proof_version", 0) or 0)

    commit_snapshot = request_json("GET", "/commit")
    verification = verify_hits(commit_snapshot, roundtrip.hits, allow_missing=False)
    assert all(verification.values()), verification

    provider_name = (roundtrip.provider or "hnsw").split("@")[0]
    for hit, proof in zip(roundtrip.hits, roundtrip.pipeline_proofs):
        if not proof:
            continue
        recomputed = recompute_pipeline_proof(
            collection=collection,
            query_vector=roundtrip.search_request.get("query_vector", roundtrip.vector),
            top_k=int(roundtrip.search_request.get("top_k", len(roundtrip.hits) or 5)),
            provider=provider_name,
            commit_root=str(roundtrip.commit_root),
            result_id=str(hit.get("id")),
        )
        assert proof == recomputed

    override_request = dict(roundtrip.search_request)
    override_request["provider"] = ALT_PROVIDER
    override_request["membership_proof"] = True
    override_request["pipeline_proof"] = True

    override_response = request_raw("POST", "/search", json_body=override_request)
    override_response.raise_for_status()
    override_payload = override_response.json()

    commit_override = override_payload.get("commit", commit_snapshot)
    override_hits = sort_hits(override_payload.get("results", []))
    verification_override = verify_hits(commit_override, override_hits, allow_missing=False)
    assert all(verification_override.values()), verification_override

    header_provider = override_response.headers.get("X-Provider-Used") or ALT_PROVIDER
    provider_override = header_provider.split("@")[0]

    for hit in override_hits:
        proof = hit.get("pipeline_proof")
        if not proof:
            continue
        recomputed = recompute_pipeline_proof(
            collection=override_request["collection"],
            query_vector=override_request["query_vector"],
            top_k=int(override_request.get("top_k", len(override_hits) or 5)),
            provider=provider_override,
            commit_root=str(commit_override.get("commit_root")),
            result_id=str(hit.get("id")),
        )
        assert proof == recomputed

    status_after = request_json("GET", f"/index/status?collection={collection}")
    proof_version_after = int(status_after.get("proof_version", 0) or 0)
    assert proof_version_after == proof_version_before
    assert status_after.get("provider") == status_before.get("provider")
