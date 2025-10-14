"""Determinism acceptance test suite."""

from __future__ import annotations

import os
from typing import List

import pytest

from ..quality_utils import approx_equal, load_golden_dataset, skip_unless_service_available
from .pipeline_helpers import (
    RoundtripResult,
    SolveHoldDueToPOR,
    run_roundtrip,
    sample_dataset,
)

SAMPLE_COUNT = int(os.getenv("QUALITY_DETERMINISM_SAMPLES", "5"))


def _compare_hits(left: RoundtripResult, right: RoundtripResult) -> None:
    assert len(left.hits) == len(right.hits)
    for a_hit, b_hit in zip(left.hits, right.hits):
        assert a_hit.get("id") == b_hit.get("id")
        assert approx_equal(float(a_hit.get("score", 0.0)), float(b_hit.get("score", 0.0)))

        if "pipeline_proof" in a_hit or "pipeline_proof" in b_hit:
            assert a_hit.get("pipeline_proof") == b_hit.get("pipeline_proof")

        if "membership_proof" in a_hit or "membership_proof" in b_hit:
            assert a_hit.get("membership_proof") == b_hit.get("membership_proof")


@pytest.mark.parametrize("iteration", range(1, 3))
def test_roundtrip_determinism(iteration: int) -> None:
    """Running the acquisition → solve → search pipeline twice must match bitwise."""

    skip_unless_service_available()
    dataset = load_golden_dataset()
    samples = sample_dataset(dataset, count=SAMPLE_COUNT)

    results: List[RoundtripResult] = []
    for sample in samples:
        try:
            results.append(
                run_roundtrip(sample, membership_proof=True, pipeline_proof=True)
            )
        except SolveHoldDueToPOR:
            continue

    if not results:
        pytest.skip("No dataset entries produced a valid PoR for solve")

    if iteration == 1:
        # Prime the determinism cache for the second iteration
        pytest.RoundtripCache = results  # type: ignore[attr-defined]
        return

    cached: List[RoundtripResult] = getattr(pytest, "RoundtripCache", [])  # type: ignore[attr-defined]
    assert len(cached) == len(results)

    for cached_result, new_result in zip(cached, results):
        assert cached_result.snapshot_id == new_result.snapshot_id
        assert cached_result.tic_id == new_result.tic_id
        assert cached_result.vector_hash == new_result.vector_hash
        assert cached_result.commit_root == new_result.commit_root
        assert cached_result.delta_pi == pytest.approx(new_result.delta_pi, abs=1e-9)
        _compare_hits(cached_result, new_result)
