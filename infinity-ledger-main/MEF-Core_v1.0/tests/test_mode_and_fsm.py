"""Regression checks for mode and gate FSM exposure."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence

import pytest
from fastapi.testclient import TestClient

MEF_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MEF_ROOT / "src"))

from api import server as api_server


def _is_strictly_decreasing(series: Sequence[float]) -> bool:
    return all(earlier > later for earlier, later in zip(series, series[1:]))


@pytest.mark.parametrize("payload", [
    {
        "asset": "integration-mode",
        "timestamp": "2025-01-01 00:00:00",
        "metrics": {"alpha": 0.42, "beta": 0.13},
    }
])
def test_solve_response_and_gate_fsm(payload):
    with TestClient(api_server.app) as client:
        headers = {"Authorization": f"Bearer {api_server.API_TOKEN}"}
        acquisition = client.post("/acquisition", json=payload)
        assert acquisition.status_code == 200
        snapshot_id = acquisition.json()["snapshot_id"]

        solve_response = client.post("/solve", params={"snapshot_id": snapshot_id}, headers=headers)
        assert solve_response.status_code == 200
        solve_payload = solve_response.json()

        assert "lyapunov_series" in solve_payload
        lyapunov_series = solve_payload["lyapunov_series"]
        assert lyapunov_series, "expected non-empty lyapunov series"
        assert _is_strictly_decreasing(lyapunov_series)

        invariants = solve_payload.get("invariants", {})
        assert "delta_pi" in invariants
        assert invariants["delta_pi"] <= api_server.EPS_PI_DEFAULT + 1e-12

        spiral_response = client.get(f"/spiral/{snapshot_id}")
        assert spiral_response.status_code == 200
        snapshot_payload = spiral_response.json()

        mode_response = client.get("/mode", headers=headers)
        assert mode_response.status_code == 200
        mode_payload = mode_response.json()

        assert mode_payload["tick_no"] == solve_payload["tick"]["tick_no"]
        assert mode_payload["tick_ms"] >= 0.0
        assert mode_payload["tick_proof"] == solve_payload["tick"]["tick_proof"]
        assert "ouroboros" in mode_payload
        assert mode_payload["ouroboros"]["phase"] in {"alpha", "beta", "gamma"}
        assert mode_payload["active_contingent"]["snapshot_id"] == snapshot_id
        assert mode_payload["active_contingent"]["tic_id"] == solve_payload["tic_id"]
        expected_mode = "commit" if solve_payload["status"] == "ok" else "hold"
        assert mode_payload["mode"] == expected_mode

        tic_response = client.get(f"/tic/{solve_payload['tic_id']}")
        assert tic_response.status_code == 200
        tic_payload = tic_response.json()

        fsm_response = client.get("/gate/fsm", headers=headers)
        assert fsm_response.status_code == 200
        fsm_payload = fsm_response.json()

        assert fsm_payload["state"] == expected_mode
        reasons = fsm_payload["reasons"]
        expected_phi = snapshot_payload["metrics"]["resonance"]
        assert abs(reasons["phi"] - expected_phi) <= 1e-9
        assert reasons["por"] == snapshot_payload["metrics"]["por"]
        assert reasons["mci"] == tic_payload["proof"].get("mci")
        if len(lyapunov_series) >= 2:
            expected_delta_v = lyapunov_series[-1] - lyapunov_series[-2]
        else:
            expected_delta_v = -abs(lyapunov_series[-1])
        assert abs(reasons["deltaV"] - expected_delta_v) <= 1e-9
        assert "t" in reasons
        assert reasons["t'"] is not None

