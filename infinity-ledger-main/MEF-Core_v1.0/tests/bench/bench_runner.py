"""Benchmark runner that measures search latency with progress reporting."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import struct

import zipfile

import numpy as np
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MEF_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MEF_ROOT))

import tests.quality_utils as quality_utils
from tests.property.pipeline_helpers import timestamp
from tests.bench.datasets import (
    build_spiral_corpus,
    generate_query_vectors,
    iter_records,
)

DEFAULT_PROBE_PORTS = (8080, 8000, 9000)


@dataclass
class TimeoutSettings:
    """Timeout configuration for benchmark HTTP requests."""

    connect: float = 30.0
    read: float = 60.0
    bulk_operation: float = 120.0


@dataclass
class RetrySettings:
    """Retry strategy configuration for benchmark HTTP requests."""

    max_attempts: int = 5
    backoff_factor: float = 2.0
    status_forcelist: Tuple[int, ...] = (429, 500, 502, 503, 504)


@dataclass
class BatchSettings:
    """Batch sizing configuration for bulk ingestion."""

    size: int = 2000
    adaptive: bool = True
    min_size: int = 500
    max_size: int = 5000

    def clamp(self, value: int) -> int:
        return max(self.min_size, min(self.max_size, value))


@dataclass
class BenchmarkConfig:
    """Loaded benchmark configuration derived from assets/bench/bench_config.json."""

    collection: str = "spiral"
    points: int = 100000
    queries: int = 200
    k: int = 10
    warmup: int = 100
    timeouts: TimeoutSettings = field(default_factory=TimeoutSettings)
    retry: RetrySettings = field(default_factory=RetrySettings)
    batch: BatchSettings = field(default_factory=BatchSettings)


def _load_bench_config() -> BenchmarkConfig:
    """Load the persisted benchmark configuration with sensible defaults."""

    path = MEF_ROOT / "assets" / "bench" / "bench_config.json"
    if not path.exists():
        return BenchmarkConfig()

    with path.open("r", encoding="utf-8") as handle:
        payload: Dict[str, Any] = json.load(handle)

    config = BenchmarkConfig(
        collection=str(payload.get("collection", "spiral")),
        points=int(payload.get("points", 100000)),
        queries=int(payload.get("queries", 200)),
        k=int(payload.get("k", 10)),
        warmup=int(payload.get("warmup", 100)),
    )

    timeouts = payload.get("timeouts", {}) or {}
    config.timeouts = TimeoutSettings(
        connect=float(timeouts.get("connect", config.timeouts.connect)),
        read=float(timeouts.get("read", config.timeouts.read)),
        bulk_operation=float(timeouts.get("bulk_operation", config.timeouts.bulk_operation)),
    )

    retry = payload.get("retry", {}) or {}
    config.retry = RetrySettings(
        max_attempts=int(retry.get("max_attempts", config.retry.max_attempts)),
        backoff_factor=float(retry.get("backoff_factor", config.retry.backoff_factor)),
        status_forcelist=tuple(retry.get("status_forcelist", list(config.retry.status_forcelist))),
    )

    batch = payload.get("batch", {}) or {}
    config.batch = BatchSettings(
        size=int(batch.get("size", config.batch.size)),
        adaptive=bool(batch.get("adaptive", config.batch.adaptive)),
        min_size=int(batch.get("min_size", config.batch.min_size)),
        max_size=int(batch.get("max_size", config.batch.max_size)),
    )

    return config


CONFIG = _load_bench_config()

_BENCH_POINTS_RAW = int(os.getenv("BENCH_POINTS", str(CONFIG.points)))
_BENCH_Q_RAW = int(os.getenv("BENCH_Q", str(CONFIG.queries)))
_BENCH_WARMUP_RAW = int(os.getenv("BENCH_WARMUP", str(CONFIG.warmup)))
_COMPARE_LIMIT = int(os.getenv("COMPARE_LIMIT", "0"))

if _COMPARE_LIMIT > 0:
    BENCH_POINTS = min(_BENCH_POINTS_RAW, _COMPARE_LIMIT)
    BENCH_Q = min(_BENCH_Q_RAW, _COMPARE_LIMIT)
    BENCH_WARMUP = min(_BENCH_WARMUP_RAW, BENCH_Q)
else:
    BENCH_POINTS = _BENCH_POINTS_RAW
    BENCH_Q = _BENCH_Q_RAW
    BENCH_WARMUP = _BENCH_WARMUP_RAW

BENCH_K = int(os.getenv("BENCH_K", str(CONFIG.k)))
UPSERT_BATCH = CONFIG.batch.clamp(int(os.getenv("UPSERT_BATCH", str(CONFIG.batch.size))))
BENCH_TIMEOUT_SECONDS = float(os.getenv("BENCH_TIMEOUT_SECONDS", "900"))

REPORT_PATH = MEF_ROOT / "assets" / "bench" / "bench_report.json"
PROGRESS_PATH = MEF_ROOT / "assets" / "bench" / "progress.log"
DEBUG_PATH = MEF_ROOT / "assets" / "bench" / "bench-debug.txt"
CORPUS_PATH = MEF_ROOT / "assets" / "bench" / "corpus.npz"
CHECKPOINT_PATH = MEF_ROOT / "assets" / "bench" / "checkpoint.json"


def _timeout(read: float) -> Tuple[float, float]:
    """Return a connect/read timeout tuple using the configured thresholds."""

    return (CONFIG.timeouts.connect, read)

QUALITY_COLLECTION = quality_utils.QUALITY_COLLECTION
QUALITY_TOKEN = quality_utils.QUALITY_TOKEN
build_session = quality_utils.build_session

try:  # Optional dependency for docker compose parsing
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    yaml = None

BASE_URL = quality_utils.QUALITY_BASE_URL.rstrip("/")


class BenchmarkTimeout(RuntimeError):
    """Raised when a benchmark stage exceeds the configured timeout."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"Benchmark timeout during {stage}")
        self.stage = stage


def _base_url() -> str:
    return BASE_URL or quality_utils.QUALITY_BASE_URL.rstrip("/")


def _set_base_url(url: str) -> None:
    global BASE_URL
    BASE_URL = url.rstrip("/")
    quality_utils.QUALITY_BASE_URL = BASE_URL


def _service_available(session: requests.Session) -> bool:
    try:
        response = session.get(
            f"{_base_url()}/healthz",
            timeout=_timeout(min(CONFIG.timeouts.read, 10.0)),
        )
        return response.status_code < 500
    except requests.RequestException:
        return False


def _percentiles(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

    sorted_values = sorted(values)

    def percentile(percent: float) -> float:
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = percent * (len(sorted_values) - 1)
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = position - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    return {
        "p50": float(percentile(0.50)),
        "p95": float(percentile(0.95)),
        "p99": float(percentile(0.99)),
    }


def _log_progress(message: str) -> None:
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _record_plan(message: str) -> None:
    DEBUG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def _load_checkpoint(total_points: int) -> Dict[str, Any]:
    """Return the persisted checkpoint if it matches the target corpus size."""

    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        payload = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if int(payload.get("total_points", 0)) != int(total_points):
        return {}
    return payload


def _write_checkpoint(state: Mapping[str, Any]) -> None:
    """Persist the current checkpoint state for recovery."""

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    serialisable = dict(state)
    CHECKPOINT_PATH.write_text(json.dumps(serialisable, indent=2), encoding="utf-8")


def _prepare_session() -> requests.Session:
    session = build_session()
    session.headers.update({"Connection": "keep-alive"})
    retry = Retry(
        total=CONFIG.retry.max_attempts,
        read=CONFIG.retry.max_attempts,
        connect=CONFIG.retry.max_attempts,
        status=CONFIG.retry.max_attempts,
        backoff_factor=CONFIG.retry.backoff_factor,
        status_forcelist=CONFIG.retry.status_forcelist,
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        pool_connections=16,
        pool_maxsize=16,
        max_retries=retry,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _check_timeout(start: float, stage: str) -> None:
    if (time.perf_counter() - start) > BENCH_TIMEOUT_SECONDS:
        raise BenchmarkTimeout(stage)


def _wait_for_bulk_job(
    session: requests.Session,
    job_id: str,
    *,
    stage_start: float,
    poll_interval: float = 0.5,
) -> Dict[str, Any]:
    """Poll the asynchronous bulk ingest job until completion."""

    status_url = f"{_base_url()}/points/bulk/{job_id}"
    interval = poll_interval

    while True:
        _check_timeout(stage_start, "ingest")
        try:
            status_response = session.get(
                status_url,
                timeout=_timeout(CONFIG.timeouts.read),
            )
        except requests.Timeout:
            interval = min(interval * 1.5, 5.0)
            time.sleep(interval)
            continue
        except requests.RequestException as exc:
            interval = min(interval * 1.5, 5.0)
            time.sleep(interval)
            _log_progress(
                f"retrying job {job_id} status after error: {exc}"
            )
            continue

        if status_response.status_code == 404:
            raise RuntimeError(f"bulk job {job_id} not found")
        if status_response.status_code >= 500:
            interval = min(interval * 1.5, 5.0)
            time.sleep(interval)
            continue
        if status_response.status_code >= 400:
            raise RuntimeError(
                f"bulk job {job_id} status request failed: HTTP {status_response.status_code}"
            )

        try:
            payload = status_response.json() if status_response.content else {}
        except ValueError as exc:
            raise RuntimeError(f"bulk job {job_id} returned invalid JSON") from exc

        status = str(payload.get("status", "")).lower()
        if status == "completed":
            return payload
        if status == "failed":
            error = payload.get("error") or "bulk ingest job failed"
            raise RuntimeError(f"bulk job {job_id} failed: {error}")

        time.sleep(interval)
        interval = min(interval * 1.5, 5.0)


def _parse_port_mapping(entry: object) -> Optional[int]:
    if isinstance(entry, str):
        token = entry.split(":", 1)[0].split("/")[0]
        return int(token) if token.isdigit() else None
    if isinstance(entry, (list, tuple)) and entry:
        head = str(entry[0]).split("/")[0]
        return int(head) if head.isdigit() else None
    if isinstance(entry, Mapping):
        for key in ("published", "host", "external", "target"):
            value = entry.get(key)
            if value is None:
                continue
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                candidate = value.split("/")[0]
                if candidate.isdigit():
                    return int(candidate)
    return None


def _compose_candidates() -> List[str]:
    compose_path = MEF_ROOT.parent / "docker-compose.yml"
    if not compose_path.exists():
        return []

    candidates: List[str] = []
    text = compose_path.read_text(encoding="utf-8")
    if yaml:
        try:
            document = yaml.safe_load(text)
        except Exception:  # pragma: no cover - parse fallback
            document = None
        if isinstance(document, Mapping):
            services = document.get("services")
            if isinstance(services, Mapping):
                for name in ("api", "app", "pcve", "service"):
                    service = services.get(name)
                    if not isinstance(service, Mapping):
                        continue
                    for entry in service.get("ports", []) or []:
                        port = _parse_port_mapping(entry)
                        if port:
                            url = f"http://localhost:{port}"
                            if url not in candidates:
                                candidates.append(url)
            if candidates:
                return candidates
    # fallback heuristic parsing
    for match in re.findall(r"(?m)^[ \t-]*\"?(\d{2,5})[:\"]", text):
        if match.isdigit():
            url = f"http://localhost:{int(match)}"
            if url not in candidates:
                candidates.append(url)
    return candidates


def _probe_url(url: str) -> bool:
    try:
        response = requests.get(
            f"{url.rstrip('/')}/healthz",
            timeout=_timeout(min(CONFIG.timeouts.read, 5.0)),
        )
        return response.status_code < 500
    except requests.RequestException:
        return False


def _resolve_base_url() -> str:
    env_url = os.getenv("QUALITY_BASE_URL", "").strip()
    candidates: List[str] = []
    if env_url:
        candidates.append(env_url)
    elif quality_utils.QUALITY_BASE_URL:
        candidates.append(quality_utils.QUALITY_BASE_URL)

    compose_candidates = _compose_candidates()
    if not env_url:
        candidates.extend(candidate for candidate in compose_candidates if candidate not in candidates)
    else:
        for candidate in compose_candidates:
            if candidate not in candidates:
                candidates.append(candidate)

    for port in DEFAULT_PROBE_PORTS:
        candidate = f"http://localhost:{port}"
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if _probe_url(candidate):
            return candidate.rstrip("/")
    return (candidates[0] if candidates else "http://localhost:8080").rstrip("/")


def _bulk_ingest(
    session: requests.Session,
    records: Iterable[dict],
    *,
    total: int,
    stage_start: float,
) -> Tuple[int, Dict[str, float]]:
    url = f"{_base_url()}/points/bulk"
    records_list = list(records)
    target_total = min(int(total), len(records_list))
    checkpoint = _load_checkpoint(target_total)
    resume_offset = min(int(checkpoint.get("ingested", 0)), target_total)
    batch_size = CONFIG.batch.clamp(int(checkpoint.get("batch_size", UPSERT_BATCH)))
    stage_durations: Dict[str, float] = {
        "ingest_ms": 0.0,
        "ingest_resume_offset": float(resume_offset),
    }
    latency_samples: List[float] = []
    per_vector_samples: List[float] = []
    job_duration_samples: List[float] = []
    job_per_vector_samples: List[float] = []
    ingested_total = resume_offset
    last_logged = resume_offset

    if resume_offset:
        _log_progress(
            f"resuming ingest from checkpoint offset={resume_offset} batch_size={batch_size}"
        )

    index = resume_offset
    while index < target_total:
        _check_timeout(stage_start, "ingest")
        window = records_list[index : min(target_total, index + batch_size)]
        if not window:
            break

        payload = {
            "collection": QUALITY_COLLECTION,
            "points": window,
            "epoch": 1,
            "metric": "cosine",
        }

        attempt_start = time.perf_counter()
        try:
            response = session.post(
                url,
                json=payload,
                timeout=_timeout(CONFIG.timeouts.bulk_operation),
            )
            response.raise_for_status()
        except requests.Timeout:
            if CONFIG.batch.adaptive and batch_size > CONFIG.batch.min_size:
                batch_size = CONFIG.batch.clamp(max(batch_size // 2, CONFIG.batch.min_size))
                _log_progress(
                    f"timeout at offset {index} – reducing batch_size to {batch_size}"
                )
                continue
            raise
        except requests.RequestException:
            raise

        try:
            response_payload = response.json() if response.content else {}
        except ValueError as exc:
            raise RuntimeError("bulk ingest response was not valid JSON") from exc

        job_id = response_payload.get("job_id")
        if not job_id:
            raise RuntimeError("bulk ingest response missing job_id")

        duration_ms = (time.perf_counter() - attempt_start) * 1000.0
        per_vector_ms = duration_ms / max(1, len(window))
        stage_durations["ingest_ms"] += duration_ms
        latency_samples.append(duration_ms)
        per_vector_samples.append(per_vector_ms)

        wait_start = time.perf_counter()
        job_result = _wait_for_bulk_job(
            session,
            job_id,
            stage_start=stage_start,
        )
        wait_ms = (time.perf_counter() - wait_start) * 1000.0
        stage_durations["ingest_job_wait_ms"] = stage_durations.get(
            "ingest_job_wait_ms", 0.0
        ) + wait_ms

        job_status = str(job_result.get("status", "")).lower()
        if job_status != "completed":
            raise RuntimeError(
                f"bulk job {job_id} finished with unexpected status={job_status or 'unknown'}"
            )

        inserted = int(job_result.get("inserted", len(window)))
        if inserted != len(window):
            raise RuntimeError(
                "bulk job %s inserted %d/%d vectors" % (job_id, inserted, len(window))
            )
        ingested_total += inserted
        index += len(window)

        if "duration_ms" in job_result:
            job_duration_samples.append(float(job_result["duration_ms"]))
        if "per_vector_ms" in job_result:
            job_per_vector_samples.append(float(job_result["per_vector_ms"]))

        if CONFIG.batch.adaptive:
            if duration_ms > CONFIG.timeouts.read * 1000.0 * 0.75 and batch_size > CONFIG.batch.min_size:
                new_size = CONFIG.batch.clamp(max(int(batch_size * 0.75), CONFIG.batch.min_size))
                if new_size != batch_size:
                    batch_size = new_size
                    _log_progress(
                        f"high latency {duration_ms:.2f}ms – shrinking batch_size to {batch_size}"
                    )
            elif duration_ms < CONFIG.timeouts.read * 1000.0 * 0.25 and batch_size < CONFIG.batch.max_size:
                increment = max(CONFIG.batch.min_size // 2, 100)
                new_size = CONFIG.batch.clamp(batch_size + increment)
                if new_size != batch_size:
                    batch_size = new_size
                    _log_progress(
                        f"latency {duration_ms:.2f}ms allows growth – batch_size now {batch_size}"
                    )

        if ingested_total - last_logged >= 5000 or ingested_total >= target_total:
            _log_progress(
                "ingested %d/%d vectors (batch=%d latency=%.2fms pv=%.4fms)"
                % (ingested_total, target_total, len(window), duration_ms, per_vector_ms)
            )
            last_logged = ingested_total

        checkpoint_state = {
            "total_points": target_total,
            "ingested": ingested_total,
            "batch_size": batch_size,
            "last_latency_ms": duration_ms,
            "per_vector_ms": per_vector_ms,
            "updated_at": timestamp(),
        }
        _write_checkpoint(checkpoint_state)

    if latency_samples:
        percentile_snapshot = _percentiles(latency_samples)
        stage_durations.update(
            {
                "ingest_batches": float(len(latency_samples)),
                "ingest_batch_latency_ms_p50": percentile_snapshot["p50"],
                "ingest_batch_latency_ms_p95": percentile_snapshot["p95"],
                "ingest_batch_latency_ms_p99": percentile_snapshot["p99"],
                "ingest_batch_latency_ms_avg": float(
                    sum(latency_samples) / len(latency_samples)
                ),
                "ingest_per_vector_ms_avg": float(
                    sum(per_vector_samples) / len(per_vector_samples)
                ),
            }
        )

    job_count = max(len(job_duration_samples), len(job_per_vector_samples))
    if job_count:
        stage_durations["ingest_job_count"] = float(job_count)

    if job_duration_samples:
        stage_durations["ingest_job_duration_ms_total"] = float(
            sum(job_duration_samples)
        )
        stage_durations["ingest_job_duration_ms_avg"] = float(
            sum(job_duration_samples) / len(job_duration_samples)
        )
    if job_per_vector_samples:
        stage_durations["ingest_job_per_vector_ms_avg"] = float(
            sum(job_per_vector_samples) / len(job_per_vector_samples)
        )

    _write_checkpoint(
        {
            "total_points": target_total,
            "ingested": ingested_total,
            "batch_size": batch_size,
            "status": "complete" if ingested_total >= target_total else "partial",
            "updated_at": timestamp(),
        }
    )

    return ingested_total, stage_durations


def _finalise_index(
    session: requests.Session,
    *,
    total: int,
    stage_start: float,
) -> Dict[str, object]:
    _log_progress("index build requested")
    _check_timeout(stage_start, "build")
    response = session.post(
        f"{_base_url()}/index/build",
        json={"collection": QUALITY_COLLECTION},
        timeout=_timeout(CONFIG.timeouts.read),
    )
    response.raise_for_status()

    attempt = 0
    while attempt < 120:
        _check_timeout(stage_start, "build")
        attempt += 1
        status_response = session.get(
            f"{_base_url()}/index/status",
            params={"collection": QUALITY_COLLECTION},
            timeout=_timeout(CONFIG.timeouts.read),
        )
        status_response.raise_for_status()
        status_payload = status_response.json()
        ready = bool(status_payload.get("ready"))
        points_indexed = int(status_payload.get("points_indexed", 0))
        _log_progress(
            "index status attempt %d: ready=%s points_indexed=%d"
            % (attempt, ready, points_indexed)
        )
        if ready and points_indexed >= total:
            params = status_payload.get("params") or {}
            _log_progress(
                "index parameters: %s"
                % json.dumps(params, sort_keys=True)
            )
            return status_payload
        time.sleep(0.5)
    raise BenchmarkTimeout("build")


def _run_queries(
    session: requests.Session,
    queries: Iterable[List[float]],
    *,
    stage: str,
    total: int,
    stage_start: float,
) -> Tuple[List[float], int, Dict[str, float]]:
    durations: List[float] = []
    failures = 0
    stage_durations = {f"{stage}_ms": 0.0}
    progress_interval = max(1, total // 10)
    plan_checks_remaining = 3 if stage == "bench" else 0

    for index, vector in enumerate(queries, start=1):
        _check_timeout(stage_start, stage)
        query_start = time.perf_counter()
        client_total_ms = 0.0
        try:
            request_start = time.perf_counter()
            response = session.post(
                f"{_base_url()}/search",
                json={
                    "collection": QUALITY_COLLECTION,
                    "query_vector": list(vector),
                    "top_k": BENCH_K,
                    "mode": "ann",
                    "solve": False,
                    "membership_proof": False,
                    "pipeline_proof": False,
                },
                timeout=_timeout(CONFIG.timeouts.read),
            )
            response.raise_for_status()
            client_total_ms = (time.perf_counter() - request_start) * 1000.0
            durations.append(client_total_ms)
            if plan_checks_remaining > 0:
                plan_checks_remaining -= 1
                plan_response = session.get(
                    f"{_base_url()}/debug/search-plan",
                    timeout=_timeout(CONFIG.timeouts.read),
                )
                plan_response.raise_for_status()
                plan_payload = plan_response.json()
                header_provider = response.headers.get("X-Provider-Used")
                if header_provider and isinstance(plan_payload, dict):
                    plan_payload.setdefault("provider_header", header_provider)
                plan_line = "search plan #%d: %s | client_total_ms=%.2f" % (
                    index,
                    json.dumps(plan_payload, sort_keys=True),
                    client_total_ms,
                )
                _log_progress(plan_line)
                _record_plan(plan_line)
                if plan_payload.get("plan") != "ann":
                    raise RuntimeError(
                        "Expected ann search plan, received %s"
                        % plan_payload.get("plan")
                    )
                counters = plan_payload.get("counters", {}) or {}
                total_vectors = float(plan_payload.get("total_vectors") or BENCH_POINTS)
                candidate_count = float(
                    counters.get("candidate_count")
                    or counters.get("visited", 0)
                )
                if total_vectors and candidate_count >= 0.9 * total_vectors:
                    raise RuntimeError(
                        "Search plan visited %.0f/%s vectors – ANN path ineffective"
                        % (candidate_count, int(total_vectors))
                    )
                timings = plan_payload.get("timings_ms") or {}
                index_ms = float(timings.get("index_search", 0.0))
                if index_ms > 100.0:
                    raise RuntimeError(
                        "Index search exceeded SLO: %.2f ms" % index_ms
                    )
                if timings and client_total_ms > 100.0 and index_ms < 2.0:
                    raise RuntimeError(
                        "Client observed %.2f ms despite %.2f ms index search"
                        % (client_total_ms, index_ms)
                    )
        except requests.RequestException:
            failures += 1
        finally:
            stage_durations[f"{stage}_ms"] += (time.perf_counter() - query_start) * 1000.0

        if index % progress_interval == 0 or index == total:
            if durations:
                _log_progress(
                    f"{stage} {index}/{total} queries processed (last_client_ms={durations[-1]:.2f})"
                )
            else:
                _log_progress(f"{stage} {index}/{total} queries processed")

    return durations, failures, stage_durations


def _write_corpus(ids: List[str], vectors: List[List[float]]) -> None:
    def _to_numpy(value: Iterable[Any], dtype: Optional[Any]) -> Optional[np.ndarray]:
        asarray = getattr(np, "asarray", None)
        if not callable(asarray):
            return None

        kwargs: Dict[str, Any] = {}
        if dtype is not None:
            kwargs["dtype"] = dtype

        try:
            try:
                array_value = asarray(value, **kwargs)
            except TypeError:
                array_value = asarray(value)
        except Exception as exc:
            _log_progress(f"numpy.asarray failed ({type(exc).__name__}): {exc}")
            return None

        ascontiguous = getattr(np, "ascontiguousarray", None)
        if callable(ascontiguous):
            try:
                array_value = ascontiguous(array_value)
            except Exception as exc:
                _log_progress(
                    "numpy.ascontiguousarray failed (%s): %s"
                    % (type(exc).__name__, exc)
                )

        return array_value if hasattr(array_value, "tobytes") else None

    array = _to_numpy(vectors, "float32")
    str_dtype = getattr(np, "str_", None)
    ids_array = _to_numpy(ids, str_dtype)

    if array is not None and ids_array is not None:
        savez = getattr(np, "savez", None)
        if callable(savez):
            try:
                savez(CORPUS_PATH, ids=ids_array, vectors=array)
                return
            except (AttributeError, TypeError, NotImplementedError) as exc:
                _log_progress(f"numpy.savez unavailable: {exc}")
            except Exception as exc:  # pragma: no cover - unexpected numpy failure
                _log_progress(f"numpy.savez failed ({type(exc).__name__}): {exc}")

        legacy_module = getattr(getattr(np, "lib", None), "npyio", None)
        legacy_savez = getattr(legacy_module, "savez", None) if legacy_module else None
        if callable(legacy_savez):
            try:
                legacy_savez(CORPUS_PATH, ids=ids_array, vectors=array)
                return
            except Exception as exc:  # pragma: no cover - legacy path failure
                _log_progress(
                    "numpy.lib.npyio.savez failed (%s): %s"
                    % (type(exc).__name__, exc)
                )

        def _dtype_descriptor(dtype: np.dtype) -> str:
            try:
                from numpy.lib import format as np_format  # type: ignore

                return np_format.dtype_to_descr(dtype)
            except Exception:
                return dtype.str

        def _shape_literal(shape: Tuple[int, ...]) -> str:
            if not shape:
                return "()"
            if len(shape) == 1:
                return f"({int(shape[0])},)"
            return "(" + ", ".join(str(int(dim)) for dim in shape) + ")"

        def _serialize(array_value: np.ndarray) -> bytes:
            descriptor = _dtype_descriptor(array_value.dtype)
            shape_literal = _shape_literal(tuple(int(dim) for dim in array_value.shape))
            header_dict = (
                "{'descr': '"
                + descriptor
                + "', 'fortran_order': False, 'shape': "
                + shape_literal
                + "}"
            )
            header_bytes = header_dict.encode("latin1")
            padding = (16 - ((len(header_bytes) + 10 + 1) % 16)) % 16
            header_bytes += b" " * padding + b"\n"
            if len(header_bytes) >= 2**16:
                raise ValueError("NPY header too large")
            payload = bytearray()
            payload.extend(b"\x93NUMPY")
            payload.extend(bytes((1, 0)))
            payload.extend(struct.pack("<H", len(header_bytes)))
            payload.extend(header_bytes)
            payload.extend(array_value.tobytes(order="C"))
            return bytes(payload)

        CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)

        try:
            compression = zipfile.ZIP_DEFLATED
            with zipfile.ZipFile(CORPUS_PATH, "w", compression=compression) as archive:
                archive.writestr("ids.npy", _serialize(ids_array))
                archive.writestr("vectors.npy", _serialize(array))
            return
        except (RuntimeError, ValueError) as exc:
            _log_progress(
                "manual NPZ compression failed (%s): %s"
                % (type(exc).__name__, exc)
            )
        except Exception as exc:
            _log_progress(
                "manual NPZ write failed (%s): %s" % (type(exc).__name__, exc)
            )

        try:
            if CORPUS_PATH.exists():
                CORPUS_PATH.unlink()
            with zipfile.ZipFile(
                CORPUS_PATH, "w", compression=zipfile.ZIP_STORED
            ) as archive:
                archive.writestr("ids.npy", _serialize(ids_array))
                archive.writestr("vectors.npy", _serialize(array))
            return
        except Exception as exc:
            _log_progress(
                "stored NPZ fallback failed (%s): %s"
                % (type(exc).__name__, exc)
            )

    def _write_json_corpus() -> None:
        CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ids": ids,
            "vectors": vectors,
        }

        try:
            with zipfile.ZipFile(CORPUS_PATH, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(
                    "corpus.json", json.dumps(payload, ensure_ascii=False).encode("utf-8")
                )
        except Exception as exc:
            _log_progress(
                "JSON corpus zip failed (%s): %s" % (type(exc).__name__, exc)
            )
            CORPUS_PATH.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )

    _log_progress("falling back to JSON corpus serialization")
    _write_json_corpus()


def run_benchmark() -> Dict[str, object]:
    PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS_PATH.write_text("", encoding="utf-8")
    DEBUG_PATH.write_text("", encoding="utf-8")

    _log_progress(
        "bench configuration: points=%d, k=%d, q=%d, batch=%d, timeout=%ss, connect=%.1fs, read=%.1fs, bulk=%.1fs"
        % (
            BENCH_POINTS,
            BENCH_K,
            BENCH_Q,
            UPSERT_BATCH,
            BENCH_TIMEOUT_SECONDS,
            CONFIG.timeouts.connect,
            CONFIG.timeouts.read,
            CONFIG.timeouts.bulk_operation,
        )
    )

    report: Dict[str, object] = {
        "status": "running",
        "generated_at": timestamp(),
        "collection": QUALITY_COLLECTION,
        "points_tested": BENCH_POINTS,
        "indexed_points": 0,
        "queries": 0,
        "successful_queries": 0,
        "failures": 0,
        "latency_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
        "metric": "cosine",
        "stage_durations_ms": {},
        "index_status": {},
    }
    _write_report(report)

    resolved_base = _resolve_base_url()
    _set_base_url(resolved_base)
    _log_progress(f"resolved base_url={resolved_base}")

    session = _prepare_session()
    token_state = "set" if QUALITY_TOKEN else "empty"
    _log_progress(
        "preflight base_url=%s token=%s" % (_base_url(), token_state)
    )

    try:
        ready = None
        for attempt in range(1, 31):
            try:
                ready = session.get(
                    f"{_base_url()}/readyz",
                    timeout=_timeout(min(CONFIG.timeouts.read, 5.0)),
                )
                if ready.status_code < 500:
                    break
            except requests.RequestException:
                ready = None
            time.sleep(1.0)
        if ready is None or ready.status_code >= 500:
            raise requests.RequestException("Service not ready within timeout")
        ready_payload = ready.json() if ready.content else {}
        collections_resp = session.get(
            f"{_base_url()}/collections",
            timeout=_timeout(CONFIG.timeouts.read),
        )
        collections_resp.raise_for_status()
        try:
            collections_payload = collections_resp.json()
        except ValueError:
            collections_payload = []
        if isinstance(collections_payload, Mapping):
            collections_count = len(collections_payload.get("collections", []))
        elif isinstance(collections_payload, list):
            collections_count = len(collections_payload)
        else:
            collections_count = 0
        report["preflight"] = {
            "readyz_status": ready.status_code,
            "ready_payload": ready_payload,
            "collections_count": collections_count,
            "base_url": _base_url(),
        }
        _write_report(report)
    except requests.RequestException as exc:
        report.update(
            {
                "status": "error",
                "stage": "preflight",
                "error": str(exc),
                "generated_at": timestamp(),
            }
        )
        _write_report(report)
        return report

    if not _service_available(session):
        report.update(
            {
                "status": "error",
                "stage": "health",
                "error": "Service not reachable",
                "generated_at": timestamp(),
            }
        )
        _write_report(report)
        return report

    try:
        ids, vectors = build_spiral_corpus(BENCH_POINTS)
        _write_corpus(ids, vectors)
        records = list(iter_records(ids, vectors))

        _log_progress("ingest start")
        ingest_start = time.perf_counter()
        indexed, stage_times = _bulk_ingest(
            session,
            records,
            total=BENCH_POINTS,
            stage_start=ingest_start,
        )
        _log_progress("ingest complete")
        report["indexed_points"] = indexed
        report.setdefault("stage_durations_ms", {}).update(stage_times)
        _write_report(report)

        build_start = time.perf_counter()
        index_status = _finalise_index(
            session,
            total=BENCH_POINTS,
            stage_start=build_start,
        )
        report["index_status"] = index_status
        _write_report(report)

        queries = generate_query_vectors(vectors, count=BENCH_Q)
        warmup_total = min(BENCH_WARMUP, len(queries))
        warmup_vectors = queries[:warmup_total]
        bench_vectors = queries
        bench_total = len(bench_vectors)

        _log_progress("warmup start")
        warmup_start = time.perf_counter()
        _warmup_durations, _warmup_failures, warmup_times = _run_queries(
            session,
            warmup_vectors,
            stage="warmup",
            total=warmup_total or 1,
            stage_start=warmup_start,
        )
        _log_progress("warmup complete")
        report.setdefault("stage_durations_ms", {}).update(warmup_times)
        _write_report(report)

        _log_progress("bench start")
        bench_start = time.perf_counter()
        bench_durations, bench_failures, bench_times = _run_queries(
            session,
            bench_vectors,
            stage="bench",
            total=bench_total or 1,
            stage_start=bench_start,
        )
        _log_progress("bench complete")
        report.setdefault("stage_durations_ms", {}).update(bench_times)

        durations = bench_durations
        failures = bench_failures

        percentiles = _percentiles(durations)
        status = "ok" if len(durations) >= max(1, bench_total) else "partial"

        report.update(
            {
                "status": status,
                "generated_at": timestamp(),
                "queries": bench_total,
                "successful_queries": len(durations),
                "failures": failures,
                "latency_ms": percentiles,
                "metric": "cosine",
            }
        )
        report.setdefault("stage_durations_ms", {}).update(
            {**stage_times, **warmup_times, **bench_times}
        )
        _write_report(report)
        return report
    except BenchmarkTimeout as exc:
        report.update(
            {
                "status": "timeout",
                "stage": exc.stage,
                "generated_at": timestamp(),
            }
        )
        _write_report(report)
        return report
    except Exception as exc:
        report.update(
            {
                "status": "error",
                "stage": "benchmark",
                "error": str(exc),
                "generated_at": timestamp(),
            }
        )
        _write_report(report)
        return report


def _write_report(payload: Dict[str, object]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    try:
        report = run_benchmark()
    except BenchmarkTimeout as exc:  # pragma: no cover - CI safeguard
        report = {
            "status": "timeout",
            "generated_at": timestamp(),
            "stage": exc.stage,
            "collection": QUALITY_COLLECTION,
            "points_tested": BENCH_POINTS,
            "indexed_points": 0,
            "queries": BENCH_Q,
            "successful_queries": 0,
            "failures": BENCH_Q,
            "latency_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "stage_durations_ms": {},
            "index_status": {},
        }
        _write_report(report)
        exit_code = 1
    except Exception as exc:  # pragma: no cover - CLI diagnostics
        report = {
            "status": "error",
            "generated_at": timestamp(),
            "error": str(exc),
            "collection": QUALITY_COLLECTION,
            "points_tested": BENCH_POINTS,
            "indexed_points": 0,
            "queries": BENCH_Q,
            "successful_queries": 0,
            "failures": BENCH_Q,
            "latency_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "stage_durations_ms": {},
            "index_status": {},
        }
        _write_report(report)
        exit_code = 1
    else:
        exit_code = 0 if report.get("status") == "ok" else 1

    print(json.dumps(report, indent=2))
    return exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
