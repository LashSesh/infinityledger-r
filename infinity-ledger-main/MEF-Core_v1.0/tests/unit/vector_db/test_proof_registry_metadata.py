from src.vector_db.proof_registry import _canonicalise_metadata


def test_keeps_non_timestamp_fields():
    meta = {
        "metrics": {"mrr": 0.42, "hits": 12},
        "stats": {"p95": 123},
        "points": [1, 2, 3],
        "runtime": 7.5,
        "checkpoints": 3,
    }
    out = _canonicalise_metadata(meta)
    assert "metrics" in out and "stats" in out and "points" in out
    assert "runtime" in out and "checkpoints" in out


def test_strips_genuine_timestamps():
    meta = {
        "timestamp": "2025-10-01T12:00:00Z",
        "created_at": "2025-10-01T12:00:00Z",
        "updatedAt": "2025-10-01T12:00:00Z",
        "event_time": 1696166400,
        "ingested_ts": 1696166400,
        "metrics": {"mrr": 0.9},
        "stats": {"p99": 999},
        "points": [1, 2],
    }
    out = _canonicalise_metadata(meta)
    for key in ["timestamp", "created_at", "updatedAt", "event_time", "ingested_ts"]:
        assert key not in out
    for key in ["metrics", "stats", "points"]:
        assert key in out


def test_combination_of_verb_and_ts_token():
    meta = {
        "generated_time": "2025-10-01T12:00:00Z",
        "update_timestamp": "2025-10-01T12:00:00Z",
        "storedDate": "2025-10-01",
        "metrics_ts_like": {"ts_in_value": "not a key"},
        "phase_ts": 123,
    }
    out = _canonicalise_metadata(meta)
    assert "generated_time" not in out
    assert "update_timestamp" not in out
    assert "phase_ts" not in out
    assert "storedDate" in out
    assert "metrics_ts_like" in out
