from __future__ import annotations

import math

from src.api.server import OperationMetrics


def test_operation_metrics_window_bound() -> None:
    metrics = OperationMetrics(maxlen=128)
    total_observations = 1_000_000
    for index in range(total_observations):
        metrics.observe("search", float(index % 7))
    snapshot = metrics.snapshot()
    assert "search" in snapshot
    data = snapshot["search"]
    assert math.isclose(data["count"], float(total_observations))
    assert data["window_count"] <= 128
    assert data["p95"] >= 0.0
    assert data["avg"] >= 0.0


