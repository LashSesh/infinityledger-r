"""Restart invariance tests (soft verification)."""

from __future__ import annotations

import pytest

from ..quality_utils import (
    load_golden_dataset,
    request_json,
    request_raw,
    skip_unless_service_available,
    sort_hits,
)
from .pipeline_helpers import SolveHoldDueToPOR, run_roundtrip, wait_for_commit_consistency


def test_commit_root_stable_across_runs() -> None:
    skip_unless_service_available()

    initial_commit = request_json("GET", "/commit")
    dataset = load_golden_dataset()
    roundtrip = None
    for sample in dataset:
        try:
            roundtrip = run_roundtrip(sample)
        except SolveHoldDueToPOR:
            continue
        if roundtrip:
            break

    if roundtrip is None:
        pytest.skip("No dataset entries produced a valid solve for restart checks")
    wait_for_commit_consistency()
    refreshed_commit = request_json("GET", "/commit")

    assert initial_commit.get("commit_root") == refreshed_commit.get("commit_root")
    assert roundtrip.commit_root == refreshed_commit.get("commit_root")


def test_provider_override_preserves_commit_root() -> None:
    skip_unless_service_available()

    dataset = load_golden_dataset()
    roundtrip = None
    for sample in dataset:
        try:
            roundtrip = run_roundtrip(sample, membership_proof=False, pipeline_proof=False)
        except SolveHoldDueToPOR:
            continue
        if roundtrip:
            break

    if roundtrip is None:
        pytest.skip("No dataset entries produced a valid solve for provider restart checks")

    body = {
        "collection": roundtrip.collection,
        "query_vector": roundtrip.vector,
        "top_k": len(roundtrip.hits) or 5,
        "mode": "ann",
        "membership_proof": False,
        "pipeline_proof": False,
    }

    baseline_response = request_raw("POST", "/search", json_body=body)
    baseline_response.raise_for_status()
    baseline_payload = baseline_response.json()
    baseline_hits = sort_hits(baseline_payload.get("results", []))
    baseline_commit = baseline_payload.get("commit", {}).get("commit_root")

    override_body = dict(body)
    override_body["provider"] = "ivf_pq"
    override_response = request_raw("POST", "/search", json_body=override_body)
    override_response.raise_for_status()

    repeat_response = request_raw("POST", "/search", json_body=body)
    repeat_response.raise_for_status()
    repeat_payload = repeat_response.json()
    repeat_hits = sort_hits(repeat_payload.get("results", []))
    repeat_commit = repeat_payload.get("commit", {}).get("commit_root")

    assert repeat_hits == baseline_hits
    assert repeat_commit == baseline_commit
