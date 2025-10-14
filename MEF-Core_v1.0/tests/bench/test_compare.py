from __future__ import annotations

import json
import os

import pytest

from tests.bench import compare_runner


def test_compare_runner_creates_artifacts(monkeypatch, tmp_path) -> None:
    targets = os.getenv("TARGETS") or "mef-core,faiss-inproc"
    monkeypatch.setenv("BENCH_COMPARE", "1")
    monkeypatch.setenv("TARGETS", targets)
    if not os.getenv("COMPARE_LIMIT"):
        monkeypatch.setenv("COMPARE_LIMIT", "32")
    if not os.getenv("COMPARE_K"):
        monkeypatch.setenv("COMPARE_K", "5")
    if not os.getenv("UPSERT_BATCH"):
        monkeypatch.setenv("UPSERT_BATCH", "16")
    if not os.getenv("ANN_METRIC"):
        monkeypatch.setenv("ANN_METRIC", "cosine")

    for path in (compare_runner.JSON_REPORT, compare_runner.MARKDOWN_REPORT):
        if path.exists():
            path.unlink()

    exit_code = compare_runner.main()
    assert exit_code == 0

    assert compare_runner.JSON_REPORT.exists(), "JSON report missing"
    assert compare_runner.MARKDOWN_REPORT.exists(), "Markdown report missing"

    payload = json.loads(compare_runner.JSON_REPORT.read_text())
    targets_payload = payload.get("targets", [])
    ok_targets = [entry for entry in targets_payload if entry.get("status") == "ok"]
    assert len(ok_targets) >= 2

    rows = [line for line in compare_runner.MARKDOWN_REPORT.read_text().splitlines() if line.startswith("| ")]
    assert len(rows) >= 4  # header + alignment + at least two data rows
