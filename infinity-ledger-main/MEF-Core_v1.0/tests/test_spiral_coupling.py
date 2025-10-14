import hashlib
from pathlib import Path

import pytest

from coupling import SpiralCouplingEngine


@pytest.fixture()
def engine(tmp_path: Path) -> SpiralCouplingEngine:
    return SpiralCouplingEngine(base_path=tmp_path)


def _expected_pipeline_proof(steps):
    base = "0" * 64
    material = (base + base + base + base + "".join(steps)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def test_pfadinvariance_and_pipeline(engine: SpiralCouplingEngine) -> None:
    seed_a = engine.inject_seed({"event": "A"})
    seed_b = engine.inject_seed({"event": "B"})

    history_p = [seed_a["resonance_seed"]["x5"], seed_b["resonance_seed"]["x5"]]
    history_q = list(reversed(history_p))

    tic_p = engine.condense_histories(history_p)
    tic_q = engine.condense_histories(history_q)

    assert tic_p["tic_id"] == tic_q["tic_id"]
    assert tic_p["invariants"]["delta_pi"] <= engine.eps_pi
    assert tic_q["invariants"]["delta_pi"] <= engine.eps_pi
    assert tic_p["proof"]["steps"]
    assert tic_p["proof"]["steps"] == tic_q["proof"]["steps"]
    assert tic_p["proof"]["pipeline_proof"] == _expected_pipeline_proof(tic_p["proof"]["steps"])


def test_hdag_sync_and_restart(tmp_path: Path) -> None:
    engine = SpiralCouplingEngine(base_path=tmp_path)
    for idx in range(4):
        engine.inject_seed({"event": idx})

    first_sync = engine.sync_hdag(0.5)
    assert first_sync["edges_added"] >= 1
    head_one = first_sync["hdag_head"]

    engine_again = SpiralCouplingEngine(base_path=tmp_path)
    second_sync = engine_again.sync_hdag(0.5)
    assert second_sync["hdag_head"] == head_one


def test_spiral_navigation(engine: SpiralCouplingEngine) -> None:
    theta_current = 0.0
    candidates = [engine.params.theta_step * i for i in range(1, 6)]
    result = engine.navigate_spiral(theta_current, candidates)

    current_coords = engine.params.coordinates(theta_current)
    expected = None
    best_score = float("-inf")
    for candidate in sorted(candidates):
        score = engine.resonance.score(current_coords, engine.params.coordinates(candidate))
        if score > best_score:
            best_score = score
            expected = candidate
    assert abs(result["theta_next"] - expected) < 1e-9
    assert abs(result["score"] - best_score) < 1e-9


def test_tic_query_and_pipeline(engine: SpiralCouplingEngine) -> None:
    seed = engine.inject_seed({"event": "baseline"})
    history = [seed["resonance_seed"]["x5"]]
    tic = engine.condense_histories(history)

    results = engine.query_tics(history[0], 1)
    assert len(results) == 1
    assert results[0]["tic_id"] == tic["tic_id"]
    assert results[0]["pipeline_proof"] == tic["proof"]["pipeline_proof"]


def test_zk_infer_deterministic(engine: SpiralCouplingEngine) -> None:
    payload = {"value": 42}
    first = engine.zk_infer(payload)
    second = engine.zk_infer(payload)
    assert first == second
    assert 0.0 <= first["lzk"] <= 2.0
