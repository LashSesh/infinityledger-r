"""Gate FSM consistency tests."""

from __future__ import annotations

import pytest

from ..quality_utils import load_golden_dataset, request_json, skip_unless_service_available
from .pipeline_helpers import SolveHoldDueToPOR, run_roundtrip


def test_gate_fsm_matches_solve_state() -> None:
    skip_unless_service_available()

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
        pytest.skip("No dataset entries produced a valid solve for gate FSM checks")

    fsm = request_json("GET", "/gate/fsm")
    assert "state" in fsm and "reasons" in fsm
    reasons = fsm["reasons"]

    if roundtrip.solve_status == "ok":
        assert fsm["state"] == "commit"
        assert reasons.get("por") == "valid"
        if reasons.get("deltaV") is not None:
            assert reasons["deltaV"] <= 1e-6
    else:
        assert fsm["state"] != "commit"

    assert reasons.get("phi") is not None
    assert reasons.get("t'") is not None
