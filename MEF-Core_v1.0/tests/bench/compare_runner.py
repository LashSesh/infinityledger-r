from __future__ import annotations

import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import List, Mapping, Sequence

import faiss
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tests.bench.compare.drivers import DRIVER_REGISTRY
from tests.bench.compare.drivers.base import Driver, SearchResults
from tests.bench.datasets import build_spiral_corpus, generate_query_vectors

ASSETS_DIR = REPO_ROOT / "assets" / "bench"
JSON_REPORT = ASSETS_DIR / "compare.json"
MARKDOWN_REPORT = ASSETS_DIR / "compare.md"

ENABLED_TOKENS = {"1", "true", "yes", "on"}
DEFAULT_TARGETS = ["mef-core", "faiss-inproc", "mef-http", "faiss-http"]


@dataclass
class TargetMetrics:
    name: str
    token: str
    status: str
    recall: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    qps: float
    reason: str | None = None

    def as_dict(self) -> Mapping[str, object]:
        payload = {
            "name": self.name,
            "token": self.token,
            "status": self.status,
            "recall@k": round(self.recall, 6),
            "p50_ms": round(self.p50_ms, 3),
            "p95_ms": round(self.p95_ms, 3),
            "p99_ms": round(self.p99_ms, 3),
            "qps": round(self.qps, 3),
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


def main() -> int:
    flag = (os.getenv("BENCH_COMPARE") or "").strip().lower()
    compare_enabled = flag in ENABLED_TOKENS
    if not compare_enabled:
        print("compare benchmarks disabled; skipping")
        return 0

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    targets_env = os.getenv("TARGETS") or os.getenv("BENCH_TARGETS")
    if targets_env:
        targets = [token.strip().lower() for token in targets_env.split(",") if token.strip()]
    else:
        targets = list(DEFAULT_TARGETS)

    if not targets:
        print("no targets requested; nothing to compare")
        _write_reports(meta={}, results=[])
        return 1

    compare_limit_env = os.getenv("COMPARE_LIMIT")
    compare_limit = int(compare_limit_env) if compare_limit_env else 500
    base_points = int(os.getenv("BENCH_POINTS", "100000"))
    if compare_limit > 0:
        corpus_size = min(base_points, compare_limit)
    else:
        corpus_size = base_points
    query_target = int(os.getenv("BENCH_Q", "200"))
    query_count = min(query_target, corpus_size) if corpus_size else 0
    k = int(os.getenv("COMPARE_K", os.getenv("BENCH_K", "10")))
    batch_size = int(os.getenv("UPSERT_BATCH", "1000"))
    metric = os.getenv("ANN_METRIC", "cosine").lower()

    ids, vectors = build_spiral_corpus(corpus_size)
    records = [
        {
            "id": identifier,
            "values": vector,
            "metadata": {"source": "bench", "index": index},
            "epoch": 1,
        }
        for index, (identifier, vector) in enumerate(zip(ids, vectors))
    ]
    queries = generate_query_vectors(vectors, count=query_count)

    oracle_hits = _build_oracle(ids, vectors, queries, k, metric)

    results: List[TargetMetrics] = []
    for token in targets:
        driver_cls = DRIVER_REGISTRY.get(token)
        if driver_cls is None:
            results.append(
                TargetMetrics(
                    name=token,
                    token=token,
                    status="missing",
                    recall=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    qps=0.0,
                    reason="driver not registered",
                )
            )
            continue

        driver: Driver = driver_cls()  # type: ignore[call-arg]
        print(f"running target {token}...")
        try:
            metrics = _run_target(driver, token, records, queries, k, batch_size, oracle_hits)
        except Exception as exc:  # pragma: no cover - defensive guard
            results.append(
                TargetMetrics(
                    name=getattr(driver, "name", token),
                    token=token,
                    status="error",
                    recall=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    qps=0.0,
                    reason=str(exc),
                )
            )
        else:
            results.append(metrics)

    success_count = sum(1 for result in results if result.status == "ok")

    meta = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "corpus_size": corpus_size,
        "query_count": len(queries),
        "k": k,
        "metric": metric,
        "targets": targets,
    }

    _write_reports(meta=meta, results=results)

    if success_count < 2:
        print("compare benchmarks produced fewer than two successful targets", file=sys.stderr)
        return 2
    return 0


def _run_target(
    driver: Driver,
    token: str,
    records: Sequence[Mapping[str, object]],
    queries: Sequence[Sequence[float]],
    k: int,
    batch_size: int,
    oracle: Sequence[Sequence[str]],
) -> TargetMetrics:
    start = time.perf_counter()
    driver.connect()
    driver.clear()
    connect_elapsed = (time.perf_counter() - start) * 1000.0
    print(f"  connected in {connect_elapsed:.2f} ms")

    for offset in range(0, len(records), batch_size):
        batch = list(records[offset : offset + batch_size])
        driver.upsert(batch)
    print(f"  loaded {len(records)} vectors")

    latencies_ms: List[float] = []
    hits: SearchResults = []
    for query in queries:
        query_start = time.perf_counter()
        result = driver.search([query], k)
        elapsed = (time.perf_counter() - query_start) * 1000.0
        latencies_ms.append(elapsed)
        if result:
            hits.append(result[0])
        else:
            hits.append([])

    recall = _recall(oracle, hits, k)
    p50, p95, p99 = _percentiles(latencies_ms)
    total_ms = sum(latencies_ms)
    qps = (len(queries) / (total_ms / 1000.0)) if total_ms else float("inf")

    status = "ok"
    reason = None
    if not hits:
        status = "error"
        reason = "no search results returned"

    return TargetMetrics(
        name=getattr(driver, "name", token),
        token=token,
        status=status,
        recall=recall,
        p50_ms=p50,
        p95_ms=p95,
        p99_ms=p99,
        qps=qps,
        reason=reason,
    )


def _percentiles(samples: Sequence[float]) -> tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0
    ordered = sorted(samples)
    return (
        _percentile(ordered, 0.50),
        _percentile(ordered, 0.95),
        _percentile(ordered, 0.99),
    )


def _percentile(samples: Sequence[float], fraction: float) -> float:
    if not samples:
        return 0.0
    if len(samples) == 1:
        return float(samples[0])
    position = fraction * (len(samples) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(samples) - 1)
    weight = position - lower
    return float(samples[lower] * (1 - weight) + samples[upper] * weight)


def _recall(oracle: Sequence[Sequence[str]], hits: SearchResults, k: int) -> float:
    if not oracle or not hits:
        return 0.0
    scores: List[float] = []
    for truth, result in zip(oracle, hits):
        top_truth = truth[: min(k, len(truth))]
        if not top_truth:
            continue
        result_ids = {identifier for identifier, _ in result[:k]}
        correct = sum(1 for identifier in top_truth if identifier in result_ids)
        scores.append(correct / float(len(top_truth)))
    return float(sum(scores) / len(scores)) if scores else 0.0


def _build_oracle(
    ids: Sequence[str],
    vectors: Sequence[Sequence[float]],
    queries: Sequence[Sequence[float]],
    k: int,
    metric: str,
) -> List[List[str]]:
    if not vectors:
        return [[] for _ in queries]
    dim = len(vectors[0])
    corpus = np.asarray(vectors, dtype="float32")
    query_matrix = np.asarray(queries, dtype="float32")
    if metric == "cosine":
        faiss.normalize_L2(corpus)
        if query_matrix.size:
            faiss.normalize_L2(query_matrix)
    index = faiss.IndexFlatL2(dim)
    index.add(corpus)
    _, indices = index.search(query_matrix, int(k))
    results: List[List[str]] = []
    for row in indices:
        results.append([ids[idx] if 0 <= idx < len(ids) else "" for idx in row])
    return results


def _write_reports(*, meta: Mapping[str, object], results: Sequence[TargetMetrics]) -> None:
    payload = {
        "meta": dict(meta),
        "targets": [result.as_dict() for result in results],
    }
    JSON_REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["# Compare Benchmarks", ""]
    if meta:
        lines.append(f"*Generated:* {meta.get('generated_at', 'unknown')}")
        lines.append(f"*Corpus:* {meta.get('corpus_size', 0)} vectors")
        lines.append(f"*Queries:* {meta.get('query_count', 0)}")
        lines.append("")
    lines.append("| Target | Status | Recall@K | p50 ms | p95 ms | QPS | Notes |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for result in results:
        notes = result.reason or ""
        lines.append(
            "| {name} | {status} | {recall:.3f} | {p50:.2f} | {p95:.2f} | {qps:.2f} | {notes} |".format(
                name=result.name,
                status=result.status,
                recall=result.recall,
                p50=result.p50_ms,
                p95=result.p95_ms,
                qps=result.qps,
                notes=notes.replace("|", "/"),
            )
        )
    MARKDOWN_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
