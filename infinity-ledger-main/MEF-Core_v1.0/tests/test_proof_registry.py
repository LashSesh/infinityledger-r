import pytest

from src.vector_db.proof_registry import _canonicalise_metadata, _is_volatile


def test_keeps_metrics_like_fields():
    meta = {"metrics": {"points": 123, "stats": {"p95": 42}}, "label": "ok"}
    assert _canonicalise_metadata(meta) == meta


def test_drops_genuine_timestamp_fields():
    meta = {
        "createdAt": "2025-10-07T12:34:56Z",
        "updated_at": "2025-10-07T12:35:56Z",
        "event_timestamp": "2025-10-07T12:36:56Z",
        "foo_ts": 1696672496,
        "kept": True,
    }
    out = _canonicalise_metadata(meta)
    assert "createdAt" not in out
    assert "updated_at" not in out
    assert "event_timestamp" not in out
    assert "foo_ts" not in out
    assert out["kept"] is True


def test_plain_ts_key_is_preserved():
    meta = {"ts": 1696672496, "metrics": {"points": 1}}
    out = _canonicalise_metadata(meta)
    assert "ts" in out
    assert "metrics" in out


def test_nested_structures_respect_rules():
    meta = {
        "metrics": {"points": 1000, "updatedAt": "2025-10-07T00:00:00Z"},
        "detail": {"score_ts": 1234567890, "stats": {"p50": 1}},
    }
    out = _canonicalise_metadata(meta)
    assert out["metrics"]["points"] == 1000
    assert out["detail"]["stats"]["p50"] == 1
    assert "updatedAt" not in out["metrics"]
    assert "score_ts" not in out["detail"]


@pytest.mark.parametrize(
    "key",
    [
        "timestamp",
        "created_at",
        "updated_time",
        "event_timestamp",
        "stored_ts",
        "generated_at",
    ],
)
def test_is_volatile_positive(key: str) -> None:
    assert _is_volatile(key)


@pytest.mark.parametrize(
    "key",
    [
        "metrics",
        "dataset_stats",
        "points",
        "points_tested",
        "status",
        "latency_ms",
        "constants",
        "ts",
    ],
)
def test_is_volatile_negative(key: str) -> None:
    assert not _is_volatile(key)
