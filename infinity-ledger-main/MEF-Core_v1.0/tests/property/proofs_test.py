"""Membership and pipeline proof verification tests."""

from __future__ import annotations

import os

import pytest

from ..quality_utils import load_golden_dataset, request_json, skip_unless_service_available
from .pipeline_helpers import SolveHoldDueToPOR, run_roundtrip, sample_dataset

sys_path_added = False

if not sys_path_added:
    import sys
    from pathlib import Path

    MEF_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(MEF_ROOT))
    sys_path_added = True

from tools.recompute_pipeline import recompute_from_search_payload
from tools.verify_membership import verify_hits

SAMPLE_COUNT = int(os.getenv("QUALITY_PROOFS_SAMPLES", "3"))


def test_membership_and_pipeline_proofs() -> None:
    skip_unless_service_available()

    dataset = load_golden_dataset()
    samples = sample_dataset(dataset, count=SAMPLE_COUNT)

    commit = request_json("GET", "/commit")

    successful = 0
    for sample in samples:
        try:
            roundtrip = run_roundtrip(sample, membership_proof=True, pipeline_proof=True)
        except SolveHoldDueToPOR:
            continue

        successful += 1
        assert roundtrip.commit_root == commit.get("commit_root")

        verification = verify_hits(commit, roundtrip.hits, allow_missing=True)
        assert all(verification.values()), f"Membership proof failed: {verification}"

        payload = dict(roundtrip.search_payload)
        payload.setdefault("request", roundtrip.search_request)
        payload.setdefault("provider_used", roundtrip.provider_used)
        if roundtrip.proof_context:
            payload.setdefault("proof_context", roundtrip.proof_context)
        header_provider = roundtrip.search_headers.get("X-Provider-Used")
        if header_provider:
            payload.setdefault("headers", {})
            payload["headers"].setdefault("X-Provider-Used", header_provider)

        assert payload.get("provider_used"), "search response missing provider_used"
        proof_context = payload.get("proof_context")
        assert isinstance(proof_context, dict) and proof_context.get("provider"), "proof_context missing provider"

        recomputed = recompute_from_search_payload(payload)

        for hit, proof in zip(roundtrip.hits, roundtrip.pipeline_proofs):
            if not proof:
                continue
            hit_id = str(hit.get("id"))
            assert proof == recomputed.get(hit_id)

    if successful == 0:
        pytest.skip("No dataset entries produced verifiable proofs due to PoR holds")
