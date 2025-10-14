"""Compute Recall@K for raw vs. Solve-Coagula stabilized queries."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np

try:
    _ = (np.load, np.float32, np.savez)
except Exception as exc:  # pragma: no cover - defensive diagnostics
    import sys

    raise RuntimeError(
        "Numpy shadowed: "
        f"np.__file__={getattr(np, '__file__', '?')}, sys.path={sys.path}"
    ) from exc
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MEF_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MEF_ROOT))

from tests.property.pipeline_helpers import timestamp
from tests.quality_utils import QUALITY_BASE_URL, QUALITY_COLLECTION, build_session

BENCH_K = int(os.getenv("BENCH_K", "10"))
_BENCH_POINTS_RAW = int(os.getenv("BENCH_POINTS", "100000"))
_BENCH_Q_RAW = int(os.getenv("BENCH_Q", "200"))
_COMPARE_LIMIT = int(os.getenv("COMPARE_LIMIT", "0"))

if _COMPARE_LIMIT > 0:
    BENCH_POINTS = min(_BENCH_POINTS_RAW, _COMPARE_LIMIT)
    BENCH_Q = min(_BENCH_Q_RAW, _COMPARE_LIMIT)
else:
    BENCH_POINTS = _BENCH_POINTS_RAW
    BENCH_Q = _BENCH_Q_RAW

EFFECTIVE_Q = max(200, BENCH_Q)
N_EXACT = min(10000, BENCH_POINTS)
BENCH_SEED = int(os.getenv("BENCH_SEED", "123"))
RECALL_EFSEARCH = int(os.getenv("RECALL_EFSEARCH", "128"))
RECALL_TOLERANCE = float(os.getenv("RECALL_TOLERANCE", "0.01"))

REPORT_PATH = MEF_ROOT / "assets" / "bench" / "recall_report.json"
CORPUS_PATH = MEF_ROOT / "assets" / "bench" / "corpus.npz"
PROGRESS_PATH = MEF_ROOT / "assets" / "bench" / "progress.log"
BENCH_REPORT_PATH = MEF_ROOT / "assets" / "bench" / "bench_report.json"


def _log_progress(message: str) -> None:
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _prepare_session() -> requests.Session:
    session = build_session()
    session.headers.update({"Connection": "keep-alive"})
    adapter = HTTPAdapter(
        max_retries=Retry(
            total=2,
            read=2,
            connect=2,
            status=2,
            backoff_factor=0.1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["POST"],
        )
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _service_available(session: requests.Session) -> bool:
    try:
        response = session.get(f"{QUALITY_BASE_URL.rstrip('/')}/healthz", timeout=5)
        return response.status_code < 500
    except requests.RequestException:
        return False


def _percentile(values: Sequence[float], percent: float) -> float:
    finite = [value for value in values if math.isfinite(value)]
    if not finite:
        return 0.0
    ordered = sorted(finite)
    if len(ordered) == 1:
        return float(ordered[0])
    position = percent * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def _load_corpus() -> Dict[str, object]:
    if not CORPUS_PATH.exists():
        raise RuntimeError("Benchmark corpus missing; run bench_runner first")
    data = np.load(CORPUS_PATH, allow_pickle=True)
    ids = data["ids"].astype(str).tolist()
    vectors = data["vectors"].astype("float32")
    if len(ids) < BENCH_POINTS or vectors.shape[0] < BENCH_POINTS:
        raise RuntimeError(
            f"Corpus size {vectors.shape[0]} smaller than required BENCH_POINTS={BENCH_POINTS}"
        )
    
    # Validate no duplicate IDs
    unique_ids = set(ids)
    if len(unique_ids) != len(ids):
        duplicate_count = len(ids) - len(unique_ids)
        raise RuntimeError(
            f"Corpus contains {duplicate_count} duplicate truth_ids. "
            "This indicates a data ingestion error. "
            "Please check bench_runner.py corpus generation logic and verify datasets.py "
            "produces unique identifiers for each vector."
        )
    
    # Validate no trivial (identical) vectors
    # Check for vectors that are exactly identical (all components equal)
    if len(vectors) > 1:
        # Use numpy's unique to find duplicate rows (identical vectors)
        _, unique_indices, unique_counts = np.unique(
            vectors, axis=0, return_index=True, return_counts=True
        )
        duplicate_vector_count = np.sum(unique_counts > 1)
        if duplicate_vector_count > 0:
            # Find indices of duplicated vectors for debugging
            duplicated_mask = unique_counts > 1
            sample_duplicates = unique_indices[duplicated_mask][:5]  # Show first 5
            sample_ids = [ids[idx] for idx in sample_duplicates if idx < len(ids)]
            raise RuntimeError(
                f"Corpus contains {duplicate_vector_count} sets of identical vectors. "
                "This indicates trivial or degenerate data. "
                f"Sample duplicate vector IDs: {sample_ids}. "
                "Please check bench_runner.py and datasets.py to ensure unique, "
                "non-trivial vectors are generated with sufficient variance."
            )
    
    metric = "cosine"
    if BENCH_REPORT_PATH.exists():
        report = json.loads(BENCH_REPORT_PATH.read_text(encoding="utf-8"))
        metric = str(report.get("metric", metric)).lower()
    if metric == "cosine":
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        normalised = vectors / norms
    else:
        normalised = vectors
    return {
        "ids": ids,
        "vectors": vectors,
        "metric": metric,
        "normalised": normalised,
    }


def _select_queries(ids: Sequence[str], limit: int) -> List[int]:
    """Select diverse query indices ensuring good distribution across the corpus.
    
    Uses stratified sampling to ensure queries span the entire corpus range,
    providing better diversity than pure random sampling.
    """
    if len(ids) < limit:
        raise RuntimeError(
            f"Requested limit {limit} exceeds available ids {len(ids)}"
        )
    if limit < EFFECTIVE_Q:
        raise RuntimeError(
            f"Recall evaluation requires at least {EFFECTIVE_Q} vectors; received {limit}"
        )
    
    rng = random.Random(BENCH_SEED)
    
    # Use stratified sampling for better diversity
    # Divide corpus into EFFECTIVE_Q equal segments and sample one from each
    segment_size = limit / EFFECTIVE_Q
    indices = []
    for i in range(EFFECTIVE_Q):
        segment_start = int(i * segment_size)
        segment_end = int((i + 1) * segment_size)
        # Randomly select one index from this segment
        selected = rng.randrange(segment_start, min(segment_end, limit))
        indices.append(selected)
    
    # Shuffle to avoid sequential order bias
    rng.shuffle(indices)
    
    _log_progress(
        f"query selection: stratified sampling from {limit} vectors, "
        f"segment_size={segment_size:.1f}, selected={len(indices)}"
    )
    
    return indices


def _condense_query(session: requests.Session, vector: np.ndarray) -> np.ndarray:
    histories = [vector.tolist()]
    seed_material = ",".join(f"{value:.6f}" for value in vector)
    digest = hashlib.sha256(seed_material.encode("utf-8")).hexdigest()
    jitter_rng = random.Random(int(digest[:16], 16))
    for _ in range(2):
        histories.append([(value + jitter_rng.uniform(-1e-4, 1e-4)) for value in vector])
    response = session.post(
        f"{QUALITY_BASE_URL.rstrip('/')}/spiral/condense",
        json={"histories": histories, "mode": "argmax_sumF"},
        timeout=(3, 3),
    )
    response.raise_for_status()
    payload = response.json()
    vector_out = payload.get("vector") or payload.get("fixpoint")
    if not isinstance(vector_out, list):
        raise RuntimeError("spiral/condense did not return a vector")
    return np.asarray(vector_out, dtype="float32")


def _brute_force_topk(
    vector: np.ndarray,
    corpus: np.ndarray,
    metric: str,
    k: int,
    *,
    normalised_corpus: Optional[np.ndarray] = None,
) -> np.ndarray:
    if metric in {"l2", "l2sq"}:
        diff = corpus - vector
        scores = -np.sum(diff * diff, axis=1)
    else:
        query_norm = float(np.linalg.norm(vector)) or 1.0
        normalised_query = vector / query_norm
        if normalised_corpus is None:
            corpus_norms = np.linalg.norm(corpus, axis=1, keepdims=True)
            corpus_norms[corpus_norms == 0.0] = 1.0
            normalised_corpus = corpus / corpus_norms
        scores = normalised_corpus @ normalised_query
    if k >= len(scores):
        order = np.argsort(scores)[::-1]
    else:
        partition = np.argpartition(scores, -k)[-k:]
        order = partition[np.argsort(scores[partition])[::-1]]
    return order


def _resolve_provider_hint(
    payload: Mapping[str, Any], headers: Mapping[str, Any]
) -> Optional[str]:
    provider_hint: Optional[str] = None
    provider_used = payload.get("provider_used")
    if isinstance(provider_used, Mapping):
        provider_hint = provider_used.get("name") or provider_used.get("provider")
    elif isinstance(provider_used, str):
        provider_hint = provider_used.split("@", 1)[0]
    proof_context = payload.get("proof_context")
    if isinstance(proof_context, Mapping):
        candidate = proof_context.get("provider")
        if candidate:
            provider_hint = provider_hint or str(candidate)
    header_provider = headers.get("X-Provider-Used")
    if header_provider and not provider_hint:
        provider_hint = header_provider.split("@", 1)[0]
    return provider_hint


def _evaluate_mode(
    *,
    label: str,
    session: requests.Session,
    queries: Iterable[np.ndarray],
    truth_vectors: np.ndarray,
    truth_vectors_normalised: np.ndarray,
    truth_ids: Sequence[str],
    metric: str,
    ef_search: Optional[int] = None,
) -> Dict[str, object]:
    recalls: List[float] = []
    latencies: List[float] = []
    progress_interval = max(1, EFFECTIVE_Q // 10)
    plan_checks_remaining = 1
    observed_provider: Optional[str] = None
    observed_plan: Optional[Dict[str, Any]] = None

    for index, query_vector in enumerate(queries, start=1):
        truth_indices = _brute_force_topk(
            query_vector,
            truth_vectors,
            metric,
            BENCH_K,
            normalised_corpus=truth_vectors_normalised,
        )
        truth_set = {truth_ids[idx] for idx in truth_indices[:BENCH_K]}

        start = time.perf_counter()
        try:
            request_payload = {
                "collection": QUALITY_COLLECTION,
                "query_vector": query_vector.tolist(),
                "top_k": BENCH_K,
                "mode": "ann",
                "solve": False,
                "membership_proof": False,
                "pipeline_proof": False,
            }
            if ef_search is not None:
                request_payload["ef_search"] = int(ef_search)
            response = session.post(
                f"{QUALITY_BASE_URL.rstrip('/')}/search",
                json=request_payload,
                timeout=(3, 3),
            )
            response.raise_for_status()
            payload = response.json()
            duration_ms = (time.perf_counter() - start) * 1000.0
            latencies.append(duration_ms)
            if isinstance(payload, Mapping):
                provider_hint = _resolve_provider_hint(payload, response.headers)
                if provider_hint and not observed_provider:
                    observed_provider = provider_hint
            if plan_checks_remaining > 0:
                plan_checks_remaining -= 1
                plan_response = session.get(
                    f"{QUALITY_BASE_URL.rstrip('/')}/debug/search-plan",
                    timeout=(3, 3),
                )
                if plan_response.status_code == 200:
                    plan_payload = plan_response.json()
                    plan_text = json.dumps(plan_payload, sort_keys=True)
                    _log_progress(f"recall {label} plan: {plan_text}")
                    observed_plan = plan_payload if isinstance(plan_payload, dict) else None
                    if observed_plan and "provider_used" in observed_plan:
                        provider_candidate = observed_plan.get("provider_used")
                        if isinstance(provider_candidate, Mapping):
                            observed_provider = observed_provider or provider_candidate.get("name")
                        elif isinstance(provider_candidate, str):
                            observed_provider = observed_provider or provider_candidate.split("@", 1)[0]
                else:
                    header_provider = response.headers.get("X-Provider-Used")
                    fallback_payload = payload if isinstance(payload, Mapping) else {}
                    fallback_provider = _resolve_provider_hint(fallback_payload, response.headers)
                    provider_msg = fallback_provider or header_provider or "unknown"
                    _log_progress(
                        "recall %s plan unavailable (%s) fallback_provider=%s"
                        % (label, plan_response.status_code, provider_msg)
                    )
                    observed_provider = observed_provider or fallback_provider or (
                        header_provider.split("@", 1)[0] if header_provider else None
                    )
        except requests.RequestException:
            recalls.append(0.0)
            latencies.append(math.inf)
            continue

        hits = payload.get("results", []) if isinstance(payload, dict) else []
        predicted = [
            str(hit.get("id") or hit.get("tic_id"))
            for hit in hits[:BENCH_K]
            if isinstance(hit, dict)
        ]
        denominator = float(min(BENCH_K, len(truth_set))) or 1.0
        overlap = len(truth_set.intersection(predicted))
        recalls.append(overlap / denominator)

        if index % progress_interval == 0 or index == EFFECTIVE_Q:
            _log_progress(f"recall {label} {index}/{EFFECTIVE_Q} queries processed")

    if len(recalls) != EFFECTIVE_Q:
        raise RuntimeError(
            f"Mode {label} produced {len(recalls)} comparable queries; expected {EFFECTIVE_Q}"
        )

    average_recall = float(sum(recalls) / len(recalls)) if recalls else 0.0
    if not (0.0 < average_recall < 1.0):
        raise RuntimeError(
            f"Mode {label} produced degenerate recall {average_recall:.4f}; check ingestion"
        )

    return {
        "mode": label,
        "k": BENCH_K,
        "queries": len(recalls),
        "recall": average_recall,
        "latency_p95_ms": _percentile(latencies, 0.95),
        "provider_used": observed_provider,
        "plan_snapshot": observed_plan,
    }


def run_recall() -> Dict[str, object]:
    if EFFECTIVE_Q < 50:
        raise RuntimeError("EFFECTIVE_Q must be at least 50 for recall evaluation")

    corpus_payload = _load_corpus()
    ids: List[str] = corpus_payload["ids"]  # type: ignore[assignment]
    vectors: np.ndarray = corpus_payload["vectors"]  # type: ignore[assignment]
    vectors_normalised: np.ndarray = corpus_payload["normalised"]  # type: ignore[assignment]
    metric: str = str(corpus_payload["metric"]).lower()

    session = _prepare_session()
    if not _service_available(session):
        raise RuntimeError("Service not reachable for recall evaluation")

    if len(ids) < N_EXACT:
        raise RuntimeError(
            f"Ground truth corpus smaller than required subset: {len(ids)} < {N_EXACT}"
        )

    truth_ids = ids[:N_EXACT]
    truth_vectors = vectors[:N_EXACT]
    truth_vectors_normalised = vectors_normalised[:N_EXACT]

    indices = _select_queries(truth_ids, N_EXACT)
    _log_progress(
        "recall start: queries=%d metric=%s efSearch=%d subset=%d"
        % (EFFECTIVE_Q, metric, RECALL_EFSEARCH, N_EXACT)
    )
    raw_queries = [np.array(truth_vectors[index], copy=True) for index in indices]

    condense_vectors = []
    _log_progress("recall condense start")
    for index, vector in enumerate(raw_queries, start=1):
        condensed = _condense_query(session, vector)
        condense_vectors.append(np.array(condensed, dtype="float32"))
        if index % max(1, EFFECTIVE_Q // 10) == 0 or index == EFFECTIVE_Q:
            _log_progress(f"recall condense {index}/{EFFECTIVE_Q}")

    raw_results = _evaluate_mode(
        label="raw",
        session=session,
        queries=raw_queries,
        truth_vectors=truth_vectors,
        truth_vectors_normalised=truth_vectors_normalised,
        truth_ids=truth_ids,
        metric=metric,
        ef_search=RECALL_EFSEARCH,
    )
    sc_results = _evaluate_mode(
        label="sc",
        session=session,
        queries=condense_vectors,
        truth_vectors=truth_vectors,
        truth_vectors_normalised=truth_vectors_normalised,
        truth_ids=truth_ids,
        metric=metric,
        ef_search=RECALL_EFSEARCH,
    )

    if (
        raw_results["recall"] - sc_results["recall"] > RECALL_TOLERANCE
        and RECALL_EFSEARCH >= 128
    ):
        raise RuntimeError(
            "Stabilised recall degraded beyond tolerance: "
            f"raw={raw_results['recall']:.4f}, sc={sc_results['recall']:.4f}"
        )

    provider_eval = raw_results.get("provider_used") or sc_results.get("provider_used")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "corpus_size": BENCH_POINTS,
        "truth_subset_size": N_EXACT,
        "metric": metric,
        "efSearch_eval": RECALL_EFSEARCH,
        "queries": EFFECTIVE_Q,
        "provider_eval": provider_eval,
        "modes": [raw_results, sc_results],
    }

    recalls = [mode["recall"] for mode in report["modes"]]
    if all(value == 0.0 for value in recalls) or all(value == 1.0 for value in recalls):
        raise RuntimeError("Degenerate recall detected; check corpus wiring")

    return report


def main() -> int:
    report = run_recall()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
