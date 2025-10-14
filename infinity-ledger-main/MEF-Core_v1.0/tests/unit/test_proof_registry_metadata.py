from src.vector_db.proof_registry import _canonicalise_metadata


def test_metrics_are_not_stripped():
    metadata = {
        "metrics": {"hits": 10, "p95": 4.2},
        "stats": {"n": 5},
        "points": [1, 2, 3],
    }
    result = _canonicalise_metadata(metadata)
    assert "metrics" in result
    assert "stats" in result
    assert "points" in result


def test_genuine_timestamps_are_stripped():
    metadata = {
        "created_at": "2025-01-01T00:00:00Z",
        "updated_ts": 1690000000,
        "snapshot_timestamp": "2025-01-02T00:00:00Z",
        "ingested_at": "2025-01-03T00:00:00Z",
        "meta": {
            "generated_at": "2025-01-04T00:00:00Z",
            "score": 0.99,
        },
    }
    result = _canonicalise_metadata(metadata)
    assert "created_at" not in result
    assert "updated_ts" not in result
    assert "snapshot_timestamp" not in result
    assert "meta" in result
    assert "generated_at" not in result["meta"]
    assert result["meta"]["score"] == 0.99


def test_camel_and_uppercase_timestamps_are_stripped():
    metadata = {
        "lastUpdatedAt": "2025-01-05T00:00:00Z",
        "EVENT_TIMESTAMP": "2025-01-06T00:00:00Z",
        "payload": {"LAST_UPDATED_AT": "2025-01-07T00:00:00Z"},
        "nonVolatile": "value",
    }

    result = _canonicalise_metadata(metadata)

    assert "lastUpdatedAt" not in result
    assert "EVENT_TIMESTAMP" not in result
    assert "payload" in result and "LAST_UPDATED_AT" not in result["payload"]
    assert result["nonVolatile"] == "value"
