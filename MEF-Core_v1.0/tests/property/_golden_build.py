"""Golden dataset builder script executed via pytest."""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Tuple

import pytest

from ..quality_utils import (
    golden_directory,
    load_golden_dataset,
    load_golden_expected,
    request_json,
    skip_unless_service_available,
)
from .pipeline_helpers import RoundtripResult, SolveHoldDueToPOR, run_roundtrip, timestamp
from tools.recompute_pipeline import recompute_from_search_payload

sys_path_added = False

if not sys_path_added:
    MEF_ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(MEF_ROOT))
    sys_path_added = True

from tools.verify_membership import verify_hits

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore

STRICT = os.getenv("GOLDEN_STRICT", "0") == "1"
TARGET_COUNT = int(os.getenv("GOLDEN_COUNT", "30"))
MIN_OK = int(os.getenv("GOLDEN_MIN_OK", str(TARGET_COUNT)))
SEED = int(os.getenv("GOLDEN_SEED", "1337"))
DATASET_COUNT = int(os.getenv("GOLDEN_DATASET_COUNT", str(TARGET_COUNT)))
ATTEMPTS_PER_SAMPLE = int(os.getenv("GOLDEN_ATTEMPTS_PER_SAMPLE", "10"))
ATTEMPTS_FACTOR = int(os.getenv("GOLDEN_ATTEMPTS_FACTOR", "5"))
RELAX_POR = os.getenv("GOLDEN_RELAX_POR", "0") == "1"
HOLD_POLICY = os.getenv("GOLDEN_HOLD_POLICY", "").strip().lower()

random.seed(SEED)
if np is not None and hasattr(np, "random"):
    try:  # pragma: no cover - optional dependency
        np.random.seed(SEED)
    except Exception:  # pragma: no cover
        pass

DATASET_SEED = 123
# Explicit CI flags ensure PoR holds are bypassed only in automation.
GOLDEN_HEADERS = {
    "X-Golden-Run": "true",
    "X-CI-Mode": "true",
    "X-Golden": "true",
}

try:
    GOLDEN_DIR = golden_directory()
except FileNotFoundError:
    GOLDEN_DIR = None


def _asset_paths(filename: str) -> List[Path]:
    primary = golden_directory(create=True)
    tests_assets = Path(__file__).resolve().parents[1] / "assets" / "golden"
    paths = [primary.joinpath(filename)]
    if tests_assets != primary:
        tests_assets.mkdir(parents=True, exist_ok=True)
        paths.append(tests_assets.joinpath(filename))
    return paths


def _write_all(paths: Iterable[Path], content: str) -> None:
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _maybe_generate_dataset() -> List[Mapping[str, object]]:
    dataset_path = golden_directory(create=True).joinpath("dataset.jsonl")
    existing: List[str] = []
    if dataset_path.exists():
        existing = [line for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(existing) >= DATASET_COUNT:
            return load_golden_dataset()

    rng = random.Random(DATASET_SEED)
    samples: List[Mapping[str, object]] = []
    lines: List[str] = []
    for index in range(DATASET_COUNT):
        payload = {
            "id": f"golden-{index:03d}",
            "text": f"Deterministic golden sample {index:03d} for spiral QA.",
            "timestamp": f"2025-01-01T00:{index:02d}:00Z",
            "attributes": {
                "theta_hint": round(rng.uniform(0.0, 6.2831), 6),
                "amplitude": round(1.0 + rng.random() * 0.5, 6),
                "phase_shift": round(rng.uniform(-0.25, 0.25), 6),
            },
        }
        samples.append(payload)
        lines.append(json.dumps(payload, sort_keys=True))

    serialized = "\n".join(lines) + "\n"
    _write_all(_asset_paths("dataset.jsonl"), serialized)

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    _write_all(_asset_paths("dataset.sha256"), f"{digest}\n")

    return samples


def _golden_paths() -> list[Path]:
    return _asset_paths("golden_expected.json")


def _mutated_sample(base: Mapping[str, object], attempt: int) -> Mapping[str, object]:
    if attempt <= 0:
        return dict(base)

    rng = random.Random(DATASET_SEED + attempt)
    clone = json.loads(json.dumps(base, sort_keys=True))
    clone_id = str(base.get("id") or f"golden-{attempt:03d}")
    clone["id"] = f"{clone_id}-retry{attempt:02d}"
    attributes = dict(clone.get("attributes", {}))
    attributes.update(
        {
            "theta_hint": round(rng.uniform(0.0, 6.2831), 6),
            "amplitude": round(1.0 + rng.random() * 0.5, 6),
            "phase_shift": round(rng.uniform(-0.25, 0.25), 6),
        }
    )
    clone["attributes"] = attributes
    clone["text"] = f"{base.get('text')} (retry {attempt})"
    return clone


def _emit_summary(
    *,
    runs_ok: int,
    holds_skipped: int,
    proof_fail: int,
    hits_empty: int,
) -> None:
    summary = (
        f"GOLDEN SUMMARY — ok:{runs_ok} hold:{holds_skipped} "
        f"proof_fail:{proof_fail} hits_empty:{hits_empty}"
    )
    _write_all(_asset_paths("golden_summary.txt"), summary + "\n")
    print(summary)


def _summarise_roundtrip(
    commit: Mapping[str, object],
    roundtrip: "RoundtripResult",
) -> Tuple[List[Mapping[str, object]], bool]:
    proof_status = verify_hits(commit, roundtrip.hits, allow_missing=False)
    payload = dict(roundtrip.search_payload)
    payload.setdefault("collection", roundtrip.collection)
    payload.setdefault("top_k", roundtrip.top_k)
    payload.setdefault("provider", roundtrip.provider)
    payload.setdefault("query_vector", roundtrip.vector)
    payload.setdefault("results", roundtrip.hits)
    payload.setdefault("provider_used", roundtrip.provider_used)
    if roundtrip.proof_context:
        payload.setdefault("proof_context", roundtrip.proof_context)
    payload.setdefault(
        "request",
        {
            "collection": roundtrip.collection,
            "query_vector": roundtrip.vector,
            "top_k": roundtrip.top_k,
            "provider": roundtrip.provider,
        },
    )
    header_provider = roundtrip.search_headers.get("X-Provider-Used")
    if header_provider:
        payload.setdefault("headers", {})
        payload["headers"].setdefault("X-Provider-Used", header_provider)
    payload["commit"] = commit
    recomputed = recompute_from_search_payload(payload)

    hits: List[Mapping[str, object]] = []
    overall_ok = True
    for hit in roundtrip.hits[:5]:
        if not isinstance(hit, Mapping):
            continue
        membership = hit.get("membership_proof") if isinstance(hit, Mapping) else None
        identifier = str(hit.get("id") or hit.get("tic_id") or "")
        membership_ok = bool(identifier) and proof_status.get(identifier, False)
        pipeline_actual = hit.get("pipeline_proof") if isinstance(hit, Mapping) else None
        pipeline_expected = recomputed.get(identifier)
        pipeline_ok = bool(pipeline_actual) and pipeline_actual == pipeline_expected
        root_hint = hit.get("root")
        if not root_hint and isinstance(membership, Mapping):
            root_hint = (
                membership.get("commit_root")
                or membership.get("root")
                or membership.get("collection_root")
            )
        hit_summary = {
            "id": identifier or None,
            "score": round(float(hit.get("score", 0.0)), 6),
            "pipeline_proof": pipeline_actual,
            "expected_pipeline_proof": pipeline_expected,
            "leaf_hash": membership.get("leaf") if isinstance(membership, Mapping) else None,
            "root": root_hint,
            "membership_ok": membership_ok,
            "pipeline_ok": pipeline_ok,
            "proof_ok": membership_ok and pipeline_ok,
        }
        hits.append(hit_summary)
        if not hit_summary["proof_ok"]:
            overall_ok = False

    return hits, overall_ok


@pytest.mark.skipif(GOLDEN_DIR is None, reason="Golden asset directory missing")
def test_build_golden_snapshot() -> None:
    skip_unless_service_available()

    dataset = _maybe_generate_dataset()
    if len(dataset) < DATASET_COUNT:
        pytest.skip("Golden dataset generation did not reach target size")
    runs: List[Dict[str, object]] = []
    skip_reason: str | None = None
    holds_skipped = 0
    proof_fail = 0
    hits_empty = 0
    runs_ok = 0
    # Allow more retries in CI to work around transient PoR holds.
    max_attempts = len(dataset) * ATTEMPTS_FACTOR
    total_attempts = 0
    per_sample_attempts = [0 for _ in dataset]

    while len(runs) < TARGET_COUNT and total_attempts < max_attempts:
        progress_made = False
        for index, sample in enumerate(dataset):
            attempt = per_sample_attempts[index]
            while (
                attempt < ATTEMPTS_PER_SAMPLE
                and len(runs) < TARGET_COUNT
                and total_attempts < max_attempts
            ):
                total_attempts += 1
                candidate = _mutated_sample(sample, attempt)
                roundtrip: RoundtripResult | None = None
                try:
                    roundtrip = run_roundtrip(
                        candidate,
                        membership_proof=True,
                        pipeline_proof=True,
                        headers=GOLDEN_HEADERS,
                    )
                except SolveHoldDueToPOR:
                    holds_skipped += 1
                    if RELAX_POR:
                        try:
                            roundtrip = run_roundtrip(
                                candidate,
                                membership_proof=True,
                                pipeline_proof=True,
                                headers=GOLDEN_HEADERS,
                                por_override=True,
                            )
                        except SolveHoldDueToPOR:
                            attempt += 1
                            time.sleep(min(0.1 * (attempt or 1), 1.0))
                            continue
                    if roundtrip is None:
                        attempt += 1
                        # short exponential-ish backoff to ease POR pressure
                        time.sleep(min(0.1 * attempt, 1.0))
                        continue

                commit_payload = request_json(
                    "GET", "/commit", headers=GOLDEN_HEADERS
                )
                hits_summary, proof_ok = _summarise_roundtrip(
                    commit_payload, roundtrip
                )

                if not hits_summary:
                    hits_empty += 1
                    _emit_summary(
                        runs_ok=runs_ok,
                        holds_skipped=holds_skipped,
                        proof_fail=proof_fail,
                        hits_empty=hits_empty,
                    )
                    pytest.fail(
                        f"Golden run {candidate.get('id')} produced no search hits"
                    )

                lyapunov_series = list(roundtrip.lyapunov_series)
                if lyapunov_series and any(
                    earlier <= later
                    for earlier, later in zip(
                        lyapunov_series, lyapunov_series[1:]
                    )
                ):
                    _emit_summary(
                        runs_ok=runs_ok,
                        holds_skipped=holds_skipped,
                        proof_fail=proof_fail,
                        hits_empty=hits_empty,
                    )
                    pytest.fail(
                        f"Lyapunov series for {candidate.get('id')} is not strictly decreasing"
                    )

                if roundtrip.delta_pi > 0.001:
                    _emit_summary(
                        runs_ok=runs_ok,
                        holds_skipped=holds_skipped,
                        proof_fail=proof_fail,
                        hits_empty=hits_empty,
                    )
                    pytest.fail(
                        f"Delta pi exceeded tolerance for {candidate.get('id')}: {roundtrip.delta_pi}"
                    )

                verified_hits = [hit for hit in hits_summary if hit.get("id")]
                if not verified_hits or not proof_ok:
                    proof_fail += 1
                    _emit_summary(
                        runs_ok=runs_ok,
                        holds_skipped=holds_skipped,
                        proof_fail=proof_fail,
                        hits_empty=hits_empty,
                    )
                    pytest.fail(
                        f"Golden run {candidate.get('id')} contains unverifiable proofs"
                    )

                run_record = {
                    "input_id": candidate.get("id"),
                    "snapshot_id": roundtrip.snapshot_id,
                    "tic_id": roundtrip.tic_id,
                    "vector_hash": roundtrip.vector_hash,
                    "lyapunov_series": roundtrip.lyapunov_series,
                    "delta_pi": roundtrip.delta_pi,
                    "provider_used": roundtrip.provider_used,
                    "proof_context": roundtrip.proof_context,
                    "hits": hits_summary,
                    "proof_ok": proof_ok,
                    "generated_at": timestamp(),
                }
                runs.append(run_record)
                runs_ok += 1
                progress_made = True
                attempt += 1
                break

            per_sample_attempts[index] = attempt
            if len(runs) >= TARGET_COUNT or total_attempts >= max_attempts:
                break

        if not progress_made:
            break

    if len(runs) < TARGET_COUNT:
        _emit_summary(
            runs_ok=runs_ok,
            holds_skipped=holds_skipped,
            proof_fail=proof_fail,
            hits_empty=hits_empty,
        )
        if STRICT and len(runs) < TARGET_COUNT:
            pytest.fail(
                f"Golden snapshot incomplete: expected {TARGET_COUNT} runs, captured {len(runs)}"
            )

        if runs_ok >= MIN_OK:
            # Partial success is acceptable when we hit the configured minimum.
            print(
                f"Golden snapshot partial: {runs_ok}/{TARGET_COUNT} (minimum {MIN_OK})"
            )
        else:
            remaining = max(TARGET_COUNT - runs_ok, 0)
            if HOLD_POLICY == "skip" and holds_skipped >= max(remaining, 1):
                skip_reason = (
                    "Golden snapshot aborted due to persistent PoR holds; "
                    f"successes={runs_ok} holds={holds_skipped}"
                )
            else:
                pytest.fail(
                    f"Golden snapshot too small: need >= {MIN_OK}, got {runs_ok}"
                )

    try:
        payload = load_golden_expected()
    except FileNotFoundError:
        payload = {}
    dataset_path = golden_directory(create=True).joinpath("dataset.jsonl")
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()

    payload.update(
        {
            "dataset_sha256": digest,
            "generated_at": timestamp(),
            "runs": runs,
            "status": "skipped" if skip_reason else "ok",
            "min_ok": MIN_OK,
            "target": TARGET_COUNT,
            "holds_skipped": holds_skipped,
        }
    )
    if skip_reason:
        payload["skip_reason"] = skip_reason

    for golden_path in _golden_paths():
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    _emit_summary(
        runs_ok=runs_ok,
        holds_skipped=holds_skipped,
        proof_fail=proof_fail,
        hits_empty=hits_empty,
    )

    if skip_reason:
        pytest.skip(skip_reason)
