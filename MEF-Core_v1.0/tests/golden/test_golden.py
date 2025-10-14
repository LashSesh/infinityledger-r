"""Golden regression test suite validating vector search proofs."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

import pytest

from ..quality_utils import (
    QUALITY_COLLECTION,
    approx_equal,
    hash_vector,
    load_golden_dataset,
    load_golden_expected,
    request_json,
    request_raw,
    skip_unless_service_available,
    sort_hits,
)
from ..property.pipeline_helpers import timestamp

MEF_ROOT = Path(__file__).resolve().parents[2]
if str(MEF_ROOT) not in sys.path:
    sys.path.insert(0, str(MEF_ROOT))

from tools.recompute_pipeline import recompute_from_search_payload
from tools.verify_membership import verify_hits

GOLDEN_REPORT_PATH = MEF_ROOT / "assets" / "golden" / "golden_report.json"
GOLDEN_HEADERS = {"X-Golden-Run": "true"}


@dataclass
class GoldenResult:
    """Result envelope for a single golden test case."""

    input_id: str
    snapshot_id: str
    tic_id: str
    vector_hash: str
    lyapunov_series: List[float]
    delta_pi: float
    proof_ok: bool
    hit: Mapping[str, Any]
    differences: List[Mapping[str, Any]]
    search_latency_ms: float
    solve_latency_ms: float

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "input_id": self.input_id,
            "snapshot_id": self.snapshot_id,
            "tic_id": self.tic_id,
            "vector_hash": self.vector_hash,
            "lyapunov_series": self.lyapunov_series,
            "delta_pi": self.delta_pi,
            "proof_ok": self.proof_ok,
            "search_latency_ms": round(self.search_latency_ms, 4),
            "solve_latency_ms": round(self.solve_latency_ms, 4),
            "hits": [dict(self.hit)],
        }
        if self.differences:
            payload["differences"] = self.differences
        return payload


def _write_report(results: Iterable[GoldenResult], *, status: str) -> None:
    GOLDEN_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialised = {
        "generated_at": timestamp(),
        "status": status,
        "runs": [result.to_dict() for result in results],
        "failures": [
            {
                "input_id": result.input_id,
                "differences": result.differences,
            }
            for result in results
            if result.differences
        ],
    }
    GOLDEN_REPORT_PATH.write_text(json.dumps(serialised, indent=2), encoding="utf-8")


def _lookup_sample(dataset: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    for entry in dataset:
        if str(entry.get("id")) == identifier:
            return entry
    raise KeyError(f"sample {identifier!r} missing from golden dataset")


def _base_payload(sample: Mapping[str, Any]) -> Dict[str, Any]:
    timestamp_value = sample.get("timestamp") or "2025-01-01T00:00:00Z"
    return {
        "id": sample.get("id"),
        "text": sample.get("text"),
        "timestamp": timestamp_value,
        "meta": {
            "quality": True,
            "source": "golden-suite",
            "dataset_id": sample.get("id"),
        },
    }


def _hit_summary(hit: Mapping[str, Any], *, pipeline_expected: Optional[str]) -> Dict[str, Any]:
    membership = hit.get("membership_proof") if isinstance(hit, Mapping) else None
    membership_leaf = None
    root_hint = hit.get("root") if isinstance(hit, Mapping) else None
    if isinstance(membership, Mapping):
        membership_leaf = membership.get("leaf")
        root_hint = root_hint or membership.get("commit_root") or membership.get("root")
    summary = {
        "id": str(hit.get("id") or hit.get("tic_id")),
        "score": float(hit.get("score", 0.0)),
        "pipeline_proof": hit.get("pipeline_proof"),
        "expected_pipeline_proof": pipeline_expected,
        "leaf_hash": membership_leaf,
        "root": root_hint,
        "membership_ok": bool(hit.get("membership_ok", True)),
        "pipeline_ok": bool(hit.get("pipeline_ok", True)),
        "proof_ok": bool(hit.get("proof_ok", True)),
    }
    return summary


def _compare(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    differences: List[Mapping[str, Any]] = []
    for field in ("score", "pipeline_proof", "leaf_hash", "root", "proof_ok"):
        expected_value = expected.get(field)
        actual_value = actual.get(field)
        if field == "score":
            if not approx_equal(float(actual_value), float(expected_value)):
                differences.append(
                    {"field": field, "expected": expected_value, "actual": actual_value}
                )
        else:
            if actual_value != expected_value:
                differences.append(
                    {"field": field, "expected": expected_value, "actual": actual_value}
                )
    return differences


def _execute_case(
    case: Mapping[str, Any],
    dataset: Iterable[Mapping[str, Any]],
) -> GoldenResult:
    sample = _lookup_sample(dataset, str(case.get("input_id")))

    acquisition = request_json(
        "POST", "/acquisition", json_body=_base_payload(sample), headers=GOLDEN_HEADERS
    )
    snapshot_id = str(acquisition.get("snapshot_id"))

    solve_start = time.perf_counter()
    solve = request_json("POST", f"/solve?snapshot_id={snapshot_id}", headers=GOLDEN_HEADERS)
    solve_latency_ms = (time.perf_counter() - solve_start) * 1000.0
    tic_id = str(solve.get("tic_id"))

    tic = request_json("GET", f"/tic/{tic_id}", headers=GOLDEN_HEADERS)
    vector = list(tic.get("fixpoint") or tic.get("vector") or [])
    vector_hash = hash_vector(vector)

    search_request = {
        "collection": QUALITY_COLLECTION,
        "query_vector": vector,
        "top_k": 1,
        "mode": "ann",
        "ef_search": 128,
        "membership_proof": True,
        "pipeline_proof": True,
    }

    search_start = time.perf_counter()
    search_response_raw = request_raw(
        "POST",
        "/search",
        json_body=search_request,
        headers=GOLDEN_HEADERS,
    )
    search_latency_ms = (time.perf_counter() - search_start) * 1000.0
    search_response_raw.raise_for_status()
    search_response = search_response_raw.json()
    search_headers: MutableMapping[str, str] = dict(search_response_raw.headers)

    hits = sort_hits(search_response.get("results", []))
    if not hits:
        raise AssertionError("search returned no hits for golden case")
    first_hit: Mapping[str, Any] = hits[0]

    commit_snapshot = search_response.get("commit") or {}
    verification = verify_hits(commit_snapshot, hits[:1], allow_missing=False)
    hit_identifier = str(first_hit.get("id") or first_hit.get("tic_id") or "")
    membership_ok = bool(hit_identifier) and verification.get(hit_identifier, False)

    payload_for_pipeline: Dict[str, Any] = dict(search_response)
    payload_for_pipeline.setdefault("request", search_request)
    provider_used = search_response.get("provider_used")
    if not provider_used:
        provider_used = search_headers.get("X-Provider-Used")
    if provider_used:
        payload_for_pipeline.setdefault("provider_used", provider_used)
    pipeline_expected_map = recompute_from_search_payload(payload_for_pipeline)
    pipeline_expected = pipeline_expected_map.get(hit_identifier)

    pipeline_actual = first_hit.get("pipeline_proof") if isinstance(first_hit, Mapping) else None
    pipeline_ok = bool(pipeline_actual) and pipeline_actual == pipeline_expected

    hit_summary = _hit_summary(
        {
            **first_hit,
            "membership_ok": membership_ok,
            "pipeline_ok": pipeline_ok,
            "proof_ok": membership_ok and pipeline_ok,
        },
        pipeline_expected=pipeline_expected,
    )

    differences = _compare(case.get("hits", [{}])[0], hit_summary)

    run_result = GoldenResult(
        input_id=str(case.get("input_id")),
        snapshot_id=snapshot_id,
        tic_id=tic_id,
        vector_hash=vector_hash,
        lyapunov_series=list(solve.get("lyapunov_series") or []),
        delta_pi=float((solve.get("invariants") or {}).get("delta_pi", 0.0)),
        proof_ok=hit_summary["proof_ok"],
        hit=hit_summary,
        differences=differences,
        search_latency_ms=search_latency_ms,
        solve_latency_ms=solve_latency_ms,
    )

    expected_hit = case.get("hits", [{}])[0]
    assert approx_equal(hit_summary["score"], expected_hit.get("score", 0.0))
    assert hit_summary["proof_ok"] is True
    assert hit_summary["root"] == expected_hit.get("root")

    assert run_result.vector_hash == case.get("vector_hash")
    assert run_result.proof_ok is True

    return run_result


@pytest.mark.golden
def test_golden_vector_search_regressions() -> None:
    """Execute all golden regressions and emit a machine-readable report."""

    skip_unless_service_available()

    dataset = load_golden_dataset()
    expected_payload = load_golden_expected()
    expected_runs = expected_payload.get("runs", [])

    results: List[GoldenResult] = []
    for case in expected_runs:
        result = _execute_case(case, dataset)
        results.append(result)

    failures = [result for result in results if result.differences]
    status = "ok" if not failures else "failed"
    _write_report(results, status=status)

    assert not failures, f"Golden regressions detected: {[failure.input_id for failure in failures]}"

