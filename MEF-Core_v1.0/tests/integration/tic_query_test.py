"""Integration test ensuring `/tic/query` returns stable results."""

from __future__ import annotations

import pytest

from ..quality_utils import approx_equal, load_golden_dataset, request_json, skip_unless_service_available
from ..property.pipeline_helpers import SolveHoldDueToPOR, run_roundtrip


def test_tic_query_top_hit_matches_roundtrip() -> None:
    skip_unless_service_available()

    dataset = load_golden_dataset()
    roundtrip = None
    for sample in dataset:
        try:
            roundtrip = run_roundtrip(sample)
            break
        except SolveHoldDueToPOR:
            continue

    if roundtrip is None:
        pytest.skip("No dataset entries produced a valid PoR for solve")

    query_response = request_json(
        "POST",
        "/tic/query",
        json_body={"vector": roundtrip.vector, "k": 3},
    )
    assert isinstance(query_response, list)
    assert query_response, "tic/query returned no results"

    top_hit = query_response[0]
    assert top_hit["tic_id"] == roundtrip.tic_id
    assert approx_equal(float(top_hit["score"]), 1.0, rel_tol=1e-5, abs_tol=1e-6)
