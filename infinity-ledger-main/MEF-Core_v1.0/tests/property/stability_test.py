"""Stability regression tests for Lyapunov series and ΔPI."""

from __future__ import annotations

import os

from ..quality_utils import (
    QUALITY_COLLECTION,
    is_monotonic_decreasing,
    load_golden_dataset,
    skip_unless_service_available,
)
import pytest

from .pipeline_helpers import SolveHoldDueToPOR, run_roundtrip, sample_dataset

SAMPLE_COUNT = int(os.getenv("QUALITY_STABILITY_SAMPLES", "5"))
EPS_PI = float(os.getenv("EPS_PI", os.getenv("MEF_EPS_PI", "0.001")))


def test_lyapunov_and_delta_pi_stability() -> None:
    skip_unless_service_available()

    dataset = load_golden_dataset()
    samples = sample_dataset(dataset, count=SAMPLE_COUNT)

    successes = 0
    for sample in samples:
        try:
            result = run_roundtrip(sample, collection=QUALITY_COLLECTION)
        except SolveHoldDueToPOR:
            continue

        successes += 1
        assert result.lyapunov_series, "Lyapunov series must not be empty"
        assert is_monotonic_decreasing(result.lyapunov_series), result.lyapunov_series
        assert result.delta_pi <= EPS_PI + 1e-12
        if result.stability is not None:
            assert 0.0 <= result.stability <= 1.0

    if successes == 0:
        pytest.skip("No dataset entries produced stable solves due to PoR holds")
