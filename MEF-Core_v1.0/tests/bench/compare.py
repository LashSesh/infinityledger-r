"""Unified benchmark runner that compares MEF with external vector stores."""

from __future__ import annotations

import json
import math
import os
import statistics
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import numpy as np

from bench.drivers import DriverUnavailable
from bench.drivers import FaissBaselineDriver
from bench.drivers import VectorStoreDriver
from bench.drivers import DRIVER_REGISTRY as EXTERNAL_DRIVER_REGISTRY
from tests.bench.compare.drivers import DRIVER_REGISTRY as COMPARE_DRIVER_REGISTRY
from tests.bench.compare.drivers.base import Driver as CompareDriver
from tests.bench.datasets import build_spiral_corpus, generate_query_vectors


class ExternalDriverAdapter(VectorStoreDriver):
    """Adapter to wrap compare drivers in the VectorStoreDriver interface."""

    def __init__(self, compare_driver: CompareDriver, metric: str = "cosine") -> None:
        super().__init__(metric=metric)
        self._driver = compare_driver
        self.name = getattr(compare_driver, "name", "adapter")

    def connect(self) -> None:
        self._driver.connect()

    def clear(self, namespace: str) -> None:
        self._driver.clear()

    def upsert(
        self,
        items: Iterable[Tuple[str, Sequence[float], Optional[Mapping[str, object]]]],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        # Convert VectorStoreDriver format to Compare driver format
        compare_items = []
        for identifier, vector, metadata in items:
            item: Dict[str, object] = {
                "id": identifier,
                "values": list(vector),
            }
            if metadata:
                item["metadata"] = dict(metadata)
            compare_items.append(item)
        self._driver.upsert(compare_items)

    def search(self, query: Sequence[float], k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        results = self._driver.search([query], k)
        if results and len(results) > 0:
            return results[0]
        return []


# Merge both driver registries with adapters for compare drivers
DRIVER_REGISTRY: Dict[str, type[VectorStoreDriver]] = {}

# Add external drivers directly
for token, driver_cls in EXTERNAL_DRIVER_REGISTRY.items():
    DRIVER_REGISTRY[token] = driver_cls

# Add compare drivers wrapped in adapters
for token, compare_driver_cls in COMPARE_DRIVER_REGISTRY.items():
    # Create a wrapper class that adapts the compare driver
    class AdaptedDriver(VectorStoreDriver):
        _compare_cls = compare_driver_cls

        def __init__(self, metric: str = "cosine") -> None:
            super().__init__(metric=metric)
            self._compare_driver = self._compare_cls()
            self.name = getattr(self._compare_driver, "name", token)

        def connect(self) -> None:
            self._compare_driver.connect()

        def clear(self, namespace: str) -> None:
            self._compare_driver.clear()

        def upsert(
            self,
            items: Iterable[Tuple[str, Sequence[float], Optional[Mapping[str, object]]]],
            namespace: str,
            batch_size: int = 1000,
        ) -> None:
            compare_items = []
            for identifier, vector, metadata in items:
                item: Dict[str, object] = {
                    "id": identifier,
                    "values": list(vector),
                }
                if metadata:
                    item["metadata"] = dict(metadata)
                compare_items.append(item)
            self._compare_driver.upsert(compare_items)

        def search(self, query: Sequence[float], k: int, namespace: str) -> Sequence[Tuple[str, float]]:
            results = self._compare_driver.search([query], k)
            if results and len(results) > 0:
                return results[0]
            return []

    DRIVER_REGISTRY[token] = AdaptedDriver
ASSETS_DIR = REPO_ROOT / "assets" / "bench"
JSON_REPORT = ASSETS_DIR / "compare.json"
MARKDOWN_REPORT = ASSETS_DIR / "compare.md"
DEFAULT_NAMESPACE = os.getenv("QUALITY_COLLECTION", "spiral")
_TARGETS_ENV = os.getenv("TARGETS") or os.getenv("BENCH_TARGETS")
_COMPARE_FLAG_RAW = os.getenv("BENCH_COMPARE")
_DISABLED_COMPARE_TOKENS = {"0", "false", "no", "off", "disabled", "disable"}
_FORCED_COMPARE_TOKENS = {"1", "true", "yes", "on", "force", "enabled"}
CONNECT_RETRY_TIMEOUT = float(os.getenv("BENCH_CONNECT_TIMEOUT", "240"))
CONNECT_RETRY_DELAY = float(os.getenv("BENCH_CONNECT_RETRY_DELAY", "2.0"))
if _COMPARE_FLAG_RAW is None:
    _COMPARE_FLAG = "auto"
else:
    _COMPARE_FLAG = _COMPARE_FLAG_RAW.strip().lower()
COMPARE_ENABLED = _COMPARE_FLAG not in _DISABLED_COMPARE_TOKENS
COMPARE_FORCED = _COMPARE_FLAG in _FORCED_COMPARE_TOKENS
DEFAULT_TARGETS = _TARGETS_ENV or ("mef,faiss,qdrant,milvus" if COMPARE_FORCED else "mef,faiss")
REQUIRED_TARGETS = [
    token
    for token in (os.getenv("REQUIRED_TARGETS") or "").split(",")
    if token.strip()
]
ALWAYS_ON_TARGETS = {"mef", "faiss", "mef-core", "faiss-inproc", "mef-http", "faiss-http"}
_BENCH_POINTS_RAW = int(os.getenv("BENCH_POINTS", "100000"))
_BENCH_QUERIES_RAW = int(os.getenv("BENCH_Q", "200"))
COMPARE_LIMIT = int(os.getenv("COMPARE_LIMIT", "0"))
if COMPARE_LIMIT > 0:
    BENCH_POINTS = min(_BENCH_POINTS_RAW, COMPARE_LIMIT)
    BENCH_QUERIES = min(_BENCH_QUERIES_RAW, COMPARE_LIMIT)
else:
    BENCH_POINTS = _BENCH_POINTS_RAW
    BENCH_QUERIES = _BENCH_QUERIES_RAW
BENCH_K = int(os.getenv("BENCH_K", "10"))
BENCH_WARMUP = int(os.getenv("BENCH_WARMUP", "10"))
UPSERT_BATCH = int(os.getenv("UPSERT_BATCH", "1000"))
BENCH_METRIC = os.getenv("BENCH_METRIC", "cosine").lower()
TARGET_REGISTRY = dict(DRIVER_REGISTRY)


@dataclass
class TargetResult:
    name: str
    token: Optional[str] = None
    recall: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    qps: float = 0.0
    errors: int = 0
    skipped: bool = False
    reason: Optional[str] = None

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        if self.errors:
            return "completed-with-errors"
        return "ok"

    def to_json(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "name": self.name,
            "recall@K": round(self.recall, 6),
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "qps": round(self.qps, 3),
            "errors": int(self.errors),
            "skipped": bool(self.skipped),
            "status": self.status,
        }
        if self.token:
            payload["token"] = self.token
        if self.reason:
            payload["reason"] = self.reason
        return payload


def _percentiles(samples: Sequence[float]) -> Tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0
    ordered = sorted(samples)
    return (
        _percentile(ordered, 0.5),
        _percentile(ordered, 0.95),
        _percentile(ordered, 0.99),
    )


def _percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    position = percent * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return float(values[lower] * (1 - weight) + values[upper] * weight)


def _recall_at_k(oracle: Sequence[str], results: Sequence[str], k: int) -> float:
    if not oracle:
        return 0.0
    top_k = set(oracle[: min(k, len(oracle))])
    if not top_k:
        return 0.0
    hits = sum(1 for identifier in results[:k] if identifier in top_k)
    return hits / float(len(top_k))


def _load_git_commit() -> str:
    try:
        import subprocess

        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
        return sha.decode("utf-8").strip()
    except Exception:  # pragma: no cover - CI fallback
        return "unknown"


def _build_dataset() -> Tuple[List[Tuple[str, Sequence[float], Mapping[str, object]]], int]:
    ids, vectors = build_spiral_corpus(BENCH_POINTS)
    metadata: List[Mapping[str, object]] = [
        {"source": "bench", "index": index} for index in range(len(ids))
    ]
    items = list(zip(ids, vectors, metadata))
    dimension = len(vectors[0]) if vectors else 0
    return items, dimension


def _build_queries(corpus: Sequence[Sequence[float]]) -> List[Sequence[float]]:
    queries = generate_query_vectors(corpus, count=BENCH_QUERIES)
    if len(queries) > BENCH_QUERIES:
        return queries[:BENCH_QUERIES]
    return queries


def _prepare_oracle(
    items: Sequence[Tuple[str, Sequence[float], Mapping[str, object]]],
    queries: Sequence[Sequence[float]],
) -> List[List[str]]:
    oracle = FaissBaselineDriver(metric=BENCH_METRIC)
    oracle.connect()
    oracle.clear(DEFAULT_NAMESPACE)
    oracle.upsert(items, DEFAULT_NAMESPACE, batch_size=len(items))
    truth: List[List[str]] = []
    for vector in queries:
        hits = oracle.search(vector, BENCH_K, DEFAULT_NAMESPACE)
        truth.append([identifier for identifier, _score in hits])
    return truth


def _iter_enabled_targets() -> List[Tuple[str, VectorStoreDriver, bool]]:
    targets: List[Tuple[str, VectorStoreDriver, bool]] = []
    for token in [part.strip().lower() for part in DEFAULT_TARGETS.split(",") if part.strip()]:
        driver_cls = TARGET_REGISTRY.get(token)
        if driver_cls is None:
            continue
        driver = driver_cls(metric=BENCH_METRIC)
        enabled = COMPARE_ENABLED or token in ALWAYS_ON_TARGETS
        if COMPARE_FORCED:
            enabled = True
        targets.append((token, driver, enabled))
    return targets


def _configured_target_names() -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for token in [part.strip().lower() for part in DEFAULT_TARGETS.split(",") if part.strip()]:
        driver_cls = TARGET_REGISTRY.get(token)
        if driver_cls is None:
            continue
        name = getattr(driver_cls, "name", token)  # type: ignore[arg-type]
        if not name:
            name = token
        pairs.append((token, str(name)))
        seen.add(token)
    for fallback in ALWAYS_ON_TARGETS:
        if fallback in seen:
            continue
        driver_cls = TARGET_REGISTRY.get(fallback)
        if driver_cls is None:
            continue
        name = getattr(driver_cls, "name", fallback)
        pairs.append((fallback, str(name)))
    return pairs


def _format_exception(exc: BaseException) -> str:
    message = str(exc)
    if not message:
        return exc.__class__.__name__
    return message


def _retryable_unavailable(exc: DriverUnavailable) -> bool:
    reason = (exc.reason or "").lower()
    if not reason:
        return False
    for keyword in (
        "not configured",
        "not installed",
        "missing credentials",
    ):
        if keyword in reason:
            return False
    return True


def _connect_with_retries(
    driver: VectorStoreDriver,
    timeout: float = CONNECT_RETRY_TIMEOUT,
    delay: float = CONNECT_RETRY_DELAY,
) -> None:
    """Connect to a driver with retries and detailed logging.
    
    This function attempts to connect to external services (e.g., Milvus, Qdrant)
    with exponential backoff. It provides detailed error messages to aid debugging
    service connectivity issues.
    """
    deadline = time.perf_counter() + timeout
    last_exc: Optional[BaseException] = None
    attempt = 0
    
    while True:
        attempt += 1
        try:
            if attempt > 1:
                print(
                    f"[{driver.name}] Connection attempt {attempt} "
                    f"(timeout in {deadline - time.perf_counter():.1f}s)...",
                    flush=True,
                )
            driver.connect()
            if attempt > 1:
                print(f"[{driver.name}] ✓ Connected successfully on attempt {attempt}", flush=True)
            return
        except DriverUnavailable as exc:
            if not _retryable_unavailable(exc):
                # Non-retryable error (e.g., not configured, missing credentials)
                print(
                    f"[{driver.name}] ✗ Connection failed (non-retryable): {exc.reason}",
                    flush=True,
                )
                raise
            last_exc = exc
            if attempt == 1:
                print(
                    f"[{driver.name}] Service unavailable, will retry: {exc.reason}",
                    flush=True,
                )
        except SystemExit as exc:
            raise DriverUnavailable(
                driver.name, f"driver exited during connect: {_format_exception(exc)}"
            ) from exc
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # pragma: no cover - network race guard
            last_exc = exc
            if attempt == 1:
                print(
                    f"[{driver.name}] Connection error, will retry: {_format_exception(exc)}",
                    flush=True,
                )
        
        now = time.perf_counter()
        if now >= deadline:
            if isinstance(last_exc, DriverUnavailable):
                print(
                    f"[{driver.name}] ✗ Failed after {attempt} attempts: {last_exc.reason}",
                    file=sys.stderr,
                    flush=True,
                )
                raise last_exc
            error_msg = (
                f"connect failed after {attempt} attempts ({timeout:.0f}s timeout): {last_exc}"
            )
            print(f"[{driver.name}] ✗ {error_msg}", file=sys.stderr, flush=True)
            raise DriverUnavailable(driver.name, error_msg)
        
        remaining = max(0.0, deadline - now)
        sleep_time = min(delay, remaining)
        if sleep_time > 0:
            time.sleep(sleep_time)


def _run_target(
    token: str,
    driver: VectorStoreDriver,
    items: Sequence[Tuple[str, Sequence[float], Mapping[str, object]]],
    queries: Sequence[Sequence[float]],
    oracle_truth: Sequence[Sequence[str]],
) -> TargetResult:
    try:
        _connect_with_retries(driver)
    except DriverUnavailable as exc:
        result = TargetResult(
            name=driver.name,
            token=token,
            skipped=True,
            reason=exc.reason,
        )
        return result
    except SystemExit as exc:  # pragma: no cover - defensive
        reason = _format_exception(exc)
        return TargetResult(
            name=driver.name,
            token=token,
            skipped=True,
            reason=f"connect aborted: {reason}",
        )
    except BaseException as exc:  # pragma: no cover - defensive
        return TargetResult(
            name=driver.name,
            token=token,
            skipped=True,
            reason=_format_exception(exc),
        )

    try:
        driver.clear(DEFAULT_NAMESPACE)
    except DriverUnavailable as exc:
        return TargetResult(name=driver.name, token=token, skipped=True, reason=exc.reason)
    except BaseException as exc:
        reason = _format_exception(exc)
        return TargetResult(
            name=driver.name,
            token=token,
            skipped=True,
            reason=f"clear failed: {reason}",
        )

    try:
        driver.upsert(items, DEFAULT_NAMESPACE, batch_size=UPSERT_BATCH)
    except BaseException as exc:
        reason = _format_exception(exc)
        return TargetResult(
            name=driver.name,
            token=token,
            skipped=True,
            reason=f"upsert failed: {reason}",
        )

    warmup = min(BENCH_WARMUP, len(queries))
    warmup_queries = list(queries[:warmup])
    if len(queries) > warmup:
        bench_indices = list(range(warmup, len(queries)))
    else:
        bench_indices = list(range(len(queries)))
    bench_queries = [queries[idx] for idx in bench_indices]

    for vector in warmup_queries:
        try:
            driver.search(vector, BENCH_K, DEFAULT_NAMESPACE)
        except BaseException:
            pass

    latencies: List[float] = []
    errors = 0
    recall_scores: List[float] = []
    start = time.perf_counter()
    for index, vector in zip(bench_indices, bench_queries):
        query_start = time.perf_counter()
        try:
            hits = driver.search(vector, BENCH_K, DEFAULT_NAMESPACE)
        except BaseException:
            errors += 1
            continue
        latency_ms = (time.perf_counter() - query_start) * 1000.0
        latencies.append(latency_ms)
        identifiers = [identifier for identifier, _score in hits]
        truth = oracle_truth[min(index, len(oracle_truth) - 1)] if oracle_truth else []
        recall_scores.append(_recall_at_k(truth, identifiers, BENCH_K))
    duration = time.perf_counter() - start
    p50, p95, p99 = _percentiles(latencies)
    qps = (len(latencies) / duration) if duration > 0 else 0.0
    recall = float(statistics.fmean(recall_scores)) if recall_scores else 0.0
    return TargetResult(
        name=driver.name,
        token=token,
        recall=recall,
        p50=p50,
        p95=p95,
        p99=p99,
        qps=qps,
        errors=errors,
    )


def _write_reports(
    commit_sha: str,
    dimension: int,
    results: Sequence[TargetResult],
    command: str,
    errors: Optional[Sequence[str]] = None,
) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    dataset_payload = {
        "points": BENCH_POINTS,
        "dim": dimension,
        "queries": BENCH_QUERIES,
        "k": BENCH_K,
        "metric": BENCH_METRIC,
    }
    json_payload = {
        "commit": commit_sha,
        "dataset": dataset_payload,
        "targets": [result.to_json() for result in results],
    }
    if errors:
        json_payload["errors"] = list(errors)
    JSON_REPORT.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    sorted_by_latency = sorted([r for r in results if not r.skipped], key=lambda r: r.p50)
    sorted_by_recall = sorted([r for r in results if not r.skipped], key=lambda r: r.recall, reverse=True)
    skipped = [r for r in results if r.skipped]

    lines = ["# Vector Store Compare Benchmark", ""]
    lines.append(f"*Commit:* `{commit_sha}`  ")
    lines.append(
        f"*Dataset:* {BENCH_POINTS} points · dim={dimension} · queries={BENCH_QUERIES} · k={BENCH_K} · metric={BENCH_METRIC}"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.extend(_render_summary_table(results))
    lines.append("")
    if errors:
        lines.append("## Errors")
        lines.append("")
        for message in errors:
            lines.append(f"- {message}")
        lines.append("")
    lines.append("## Sorted by p50 latency (lower is better)")
    lines.append("")
    lines.extend(_render_table(sorted_by_latency))
    lines.append("")
    lines.append("## Sorted by recall@K (higher is better)")
    lines.append("")
    lines.extend(_render_table(sorted_by_recall))
    lines.append("")
    if skipped:
        lines.append("## Skipped Targets")
        lines.append("")
        for entry in skipped:
            reason = entry.reason or "not available"
            lines.append(f"- **{entry.name}** — {reason}")
        lines.append("")
    lines.append("## Command")
    lines.append("")
    lines.append(f"`{command}`")
    lines.append("")
    env_summary = f"TARGETS={DEFAULT_TARGETS} BENCH_METRIC={BENCH_METRIC}"
    lines.append(f"Environment: `{env_summary}`")

    MARKDOWN_REPORT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_failure_reports(command: str, error: BaseException) -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    commit_sha = _load_git_commit()
    message = str(error) or error.__class__.__name__
    stack = "".join(traceback.format_exception(error)).strip()
    results = [
        TargetResult(
            name=display,
            token=token,
            skipped=True,
            reason=f"compare failed: {message}",
        )
        for token, display in _configured_target_names()
    ]
    dataset_payload = {
        "points": BENCH_POINTS,
        "dim": 0,
        "queries": BENCH_QUERIES,
        "k": BENCH_K,
        "metric": BENCH_METRIC,
    }
    json_payload = {
        "commit": commit_sha,
        "dataset": dataset_payload,
        "targets": [result.to_json() for result in results],
        "error": message,
    }
    if stack:
        json_payload["traceback"] = stack
    JSON_REPORT.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    lines = ["# Vector Store Compare Benchmark", ""]
    lines.append(f"*Commit:* `{commit_sha}`  ")
    lines.append(
        f"*Dataset:* {BENCH_POINTS} points · dim=unknown · queries={BENCH_QUERIES} · k={BENCH_K} · metric={BENCH_METRIC}"
    )
    lines.append("")
    lines.append("## Failure")
    lines.append("")
    lines.append(f"Compare benchmark failed: {message}")
    if stack:
        lines.append("")
        lines.append("```")
        lines.append(stack)
        lines.append("```")
    lines.append("")
    if results:
        lines.append("## Skipped Targets")
        lines.append("")
        lines.extend(_render_table(results))
        lines.append("")
    lines.append("## Command")
    lines.append("")
    lines.append(f"`{command}`")
    lines.append("")
    env_summary = f"TARGETS={DEFAULT_TARGETS} BENCH_METRIC={BENCH_METRIC}"
    lines.append(f"Environment: `{env_summary}`")

    MARKDOWN_REPORT.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _render_table(rows: Sequence[TargetResult]) -> List[str]:
    if not rows:
        return ["_No successful targets._"]
    header = "| Target | Status | recall@K | p50 (ms) | p95 (ms) | p99 (ms) | QPS | Errors | Reason |"
    separator = "|---|---|---|---|---|---|---|---|---|"
    lines = [header, separator]
    for row in rows:
        lines.append(
            "| {name} | {status} | {recall:.3f} | {p50:.2f} | {p95:.2f} | {p99:.2f} | {qps:.1f} | {errors} | {reason} |".format(
                name=row.name,
                status=row.status,
                recall=row.recall,
                p50=row.p50,
                p95=row.p95,
                p99=row.p99,
                qps=row.qps,
                errors=row.errors,
                reason=row.reason or "",
            )
        )
    return lines


def _render_summary_table(rows: Sequence[TargetResult]) -> List[str]:
    if not rows:
        return ["_No targets configured._"]
    return _render_table(rows)


def main() -> int:
    command = "python -m tests.bench.compare"
    try:
        items, dimension = _build_dataset()
        queries = _build_queries([vector for _, vector, _ in items])
        truth = _prepare_oracle(items, queries)
        results: List[TargetResult] = []
        results_by_token: Dict[str, TargetResult] = {}
        for token, driver, enabled in _iter_enabled_targets():
            if not enabled:
                results.append(
                    TargetResult(
                        name=driver.name,
                        token=token,
                        skipped=True,
                        reason="compare disabled",
                    )
                )
                results_by_token[token] = results[-1]
                continue
            result = _run_target(token, driver, items, queries, truth)
            results.append(result)
            results_by_token[token] = result
        commit_sha = _load_git_commit()
        ok_targets = [result for result in results if result.status == "ok"]
        exit_code = 0
        error_messages: List[str] = []
        if COMPARE_FORCED and len(ok_targets) < 2:
            ok_names = ", ".join(result.name for result in ok_targets) or "none"
            error_messages.append(
                f"compare requires at least two successful targets, found {len(ok_targets)} ({ok_names})"
            )
            exit_code = max(exit_code, 2)

        required_tokens = {token.strip().lower() for token in REQUIRED_TARGETS}
        if required_tokens:
            missing = sorted(token for token in required_tokens if token not in results_by_token)
            failing = sorted(
                token
                for token in required_tokens
                if token in results_by_token and results_by_token[token].status != "ok"
            )
            if missing:
                error_messages.append(
                    "required compare targets missing: " + ", ".join(missing)
                )
                exit_code = max(exit_code, 2)
            if failing:
                failure_notes = ", ".join(
                    f"{token} ({results_by_token[token].status})" for token in failing
                )
                error_messages.append(
                    "required compare targets failed: " + failure_notes
                )
                exit_code = max(exit_code, 2)

        _write_reports(commit_sha, dimension, results, command, errors=error_messages)

        if COMPARE_FORCED:
            missing_artifacts = [
                path.name
                for path in (JSON_REPORT, MARKDOWN_REPORT)
                if not path.exists() or path.stat().st_size == 0
            ]
            if missing_artifacts:
                error_messages.append(
                    "compare artifacts missing: " + ", ".join(sorted(missing_artifacts))
                )
                exit_code = max(exit_code, 2)
                _write_reports(commit_sha, dimension, results, command, errors=error_messages)

        payload: Dict[str, object] = {"results": [r.to_json() for r in results]}
        if error_messages:
            payload["errors"] = error_messages
        print(json.dumps(payload, indent=2))

        if error_messages:
            for message in error_messages:
                print(message, file=sys.stderr)
        return exit_code
    except BaseException as exc:  # pragma: no cover - defensive fail-safe
        _write_failure_reports(command, exc)
        print(
            json.dumps({"error": _format_exception(exc)}),
            file=sys.stderr,
        )
        if isinstance(exc, SystemExit):
            code = exc.code
            if isinstance(code, int) and code > 0:
                return code
            return 1
        return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
