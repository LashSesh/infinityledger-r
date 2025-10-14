from src.vector_db.providers import IVFPQProvider


def _records():
    return {
        "vec_a": {"vector": [1.0, 0.0]},
        "vec_b": {"vector": [0.0, 1.0]},
        "vec_c": {"vector": [1.0, 1.0]},
    }


def test_ivfpq_respects_l2_metric():
    provider = IVFPQProvider(seed=0, probes=10, metric="l2")
    records = _records()
    provider.build(records)

    query = [0.0, 1.0]
    results = provider.search(query, records, top_k=3)

    assert results[0][0] == "vec_b"
    assert all(name in {"vec_a", "vec_b", "vec_c"} for name, _ in results)

    plan = provider.get_last_plan()
    assert plan is not None
    assert plan["params"]["metric"] == "l2"


def test_ivfpq_defaults_to_cosine_similarity():
    provider = IVFPQProvider(seed=0, probes=10)
    records = _records()
    provider.build(records)

    query = [1.0, 0.0]
    results = provider.search(query, records, top_k=3)

    assert results[0][0] == "vec_a"
    plan = provider.get_last_plan()
    assert plan is not None
    assert plan["params"]["metric"] == "cosine"
