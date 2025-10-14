"""Smoke tests for the golden snapshot builder configuration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import List

import pytest


def _prepare_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Reload the golden module with deterministic paths and env."""

    monkeypatch.setenv("GOLDEN_DATASET_COUNT", "1")
    monkeypatch.setenv("GOLDEN_COUNT", "1")
    monkeypatch.setenv("GOLDEN_MIN_OK", "1")
    monkeypatch.setenv("GOLDEN_ATTEMPTS_PER_SAMPLE", "2")
    monkeypatch.setenv("GOLDEN_ATTEMPTS_FACTOR", "20")
    monkeypatch.setenv("GOLDEN_HOLD_POLICY", "")
    monkeypatch.setenv("GOLDEN_RELAX_POR", "1")
    monkeypatch.setenv("GOLDEN_STRICT", "0")

    from tests.property import _golden_build as golden

    module = importlib.reload(golden)
    module.GOLDEN_DIR = tmp_path
    monkeypatch.setattr(module, "golden_directory", lambda create=False: tmp_path)
    monkeypatch.setattr(module, "_asset_paths", lambda filename: [tmp_path / filename])
    monkeypatch.setattr(module, "skip_unless_service_available", lambda: None)

    dataset_sample = {
        "id": "golden-000",
        "text": "sample",
        "timestamp": "2025-01-01T00:00:00Z",
        "attributes": {"theta_hint": 0.1, "amplitude": 1.0, "phase_shift": 0.0},
    }

    def _fake_dataset() -> List[dict]:
        dataset_path = tmp_path / "dataset.jsonl"
        dataset_path.write_text(json.dumps(dataset_sample) + "\n", encoding="utf-8")
        return [dict(dataset_sample)]

    monkeypatch.setattr(module, "_maybe_generate_dataset", _fake_dataset)
    monkeypatch.setattr(module, "load_golden_expected", lambda: {})
    monkeypatch.setattr(module, "timestamp", lambda: "2025-01-01T00:00:00Z")

    def _fake_request_json(method: str, path: str, **_kwargs):
        if path == "/commit":
            return {"commit_root": "abc123"}
        raise AssertionError(f"unexpected request_json call: {method} {path}")

    monkeypatch.setattr(module, "request_json", _fake_request_json)

    class _Roundtrip:
        snapshot_id = "snap-1"
        tic_id = "tic-1"
        vector_hash = "deadbeef"
        lyapunov_series = [5.0, 4.0, 3.0]
        delta_pi = 0.0
        provider_used = "mef"
        proof_context = None

    calls: list[bool] = []

    def _fake_roundtrip(sample, **kwargs):
        por_override = kwargs.get("por_override", False)
        calls.append(por_override)
        if not por_override and len(calls) == 1:
            raise module.SolveHoldDueToPOR("snap-1", "hold", {})
        return _Roundtrip()

    monkeypatch.setattr(module, "run_roundtrip", _fake_roundtrip)
    monkeypatch.setattr(
        module,
        "_summarise_roundtrip",
        lambda commit, roundtrip: ([{"id": "doc-1", "proof_ok": True}], True),
    )

    return module, calls


def test_golden_builder_respects_env_and_por_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module, calls = _prepare_module(monkeypatch, tmp_path)

    module.test_build_golden_snapshot()

    assert calls == [False, True]

    golden_payload = json.loads((tmp_path / "golden_expected.json").read_text())
    assert len(golden_payload["runs"]) == 1
    assert golden_payload["status"] == "ok"
    assert golden_payload["min_ok"] == 1
    assert golden_payload["target"] == 1
    assert golden_payload["holds_skipped"] == 1
    assert "skip_reason" not in golden_payload
    assert module.ATTEMPTS_PER_SAMPLE == 2
    assert module.ATTEMPTS_FACTOR == 20
    assert module.DATASET_COUNT == 1
    assert module.TARGET_COUNT == 1
    assert module.MIN_OK == 1
