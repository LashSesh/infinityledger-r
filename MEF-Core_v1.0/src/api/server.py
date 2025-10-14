"""
MEF-Core API Server - SPEC-002-konform
FastAPI mit orjson für deterministische JSON-Serialisierung.
"""

import asyncio
import logging
import os
import random
import sys  # falls genutzt
import hashlib  # falls genutzt
import json
import threading
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Deque, Mapping  # falls genutzt
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from prometheus_client import (
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
import uvicorn
import orjson
import numpy as np
import yaml

# Import MEF-Core Module
from ingestion.triton_core import normalize_payload
from spiral.snapshot import SpiralSnapshot
from spiral.storage import SpiralStorage
from spiral.proof_of_resonance import ProofOfResonance
from solvecoagula.operators import SolveCoagula
from tic.crystallizer import TICCrystallizer
from ledger.mef_block import MEFLedger
from hdag.graph import HDAG
from audit.logger import MEFAuditLogger
from vector_db.index_manager import IndexManager
from vector_db.manifest_store import ManifestStore
from vector_db.proof_registry import ProofRegistry
from coupling import SpiralCouplingEngine

# SPEC-002: Deterministische JSON-Response Klasse
class ORJSONResponse(Response):
    media_type = "application/json"
    
    def render(self, content: Any) -> bytes:
        return orjson.dumps(
            content,
            option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2
        )

# FastAPI App mit custom Response
app = FastAPI(
    title="MEF-Core API - SPEC-002",
    version="1.0.0",
    default_response_class=ORJSONResponse
)

SEARCH_LOGGER = logging.getLogger("mef.search-plan")
if not SEARCH_LOGGER.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    SEARCH_LOGGER.addHandler(handler)
SEARCH_LOGGER.setLevel(logging.INFO)

CONFIG_LOGGER = logging.getLogger("mef.config")
if not CONFIG_LOGGER.handlers:
    config_handler = logging.StreamHandler(sys.stdout)
    config_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    CONFIG_LOGGER.addHandler(config_handler)
CONFIG_LOGGER.setLevel(logging.INFO)

# Konfiguration
CONFIG_PATH = Path("config.yaml")
STORE_PATH = Path(os.getenv("MEF_STORE_DIR", str(Path.home() / "mef" / "store")))
LEDGER_PATH = Path(os.getenv("MEF_LEDGER_DIR", str(Path.home() / "mef" / "ledger")))
LOGS_PATH = Path(os.getenv("MEF_LOGS_DIR", str(Path.home() / "mef" / "logs")))
def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


API_TOKEN = os.getenv("MEF_API_TOKEN", "infinity-ledger-token")
AUTH_TOKEN_REQUIRED = _as_bool(os.getenv("AUTH_TOKEN_REQUIRED"), default=True)
EPS_PI_DEFAULT = float(os.getenv("MEF_EPS_PI", "0.001"))
QUALITY_COLLECTION = (os.getenv("QUALITY_COLLECTION") or "spiral").strip() or "spiral"
QUALITY_METRIC = (os.getenv("QUALITY_METRIC") or "cosine").strip().lower() or "cosine"
QUALITY_PROVIDER_ENV = (os.getenv("QUALITY_PROVIDER") or "").strip().lower() or None

CONFIG_LOGGER.info(
    "auth_required=%s token_set=%s",
    AUTH_TOKEN_REQUIRED,
    bool(API_TOKEN),
)


class OperationMetrics:
    """Latency collector with bounded in-memory window for diagnostics."""

    def __init__(self, maxlen: Optional[int] = None) -> None:
        window = int(os.getenv("METRICS_WINDOW", "10000")) if maxlen is None else int(maxlen)
        if window <= 0:
            raise ValueError("METRICS_WINDOW must be positive")
        self._maxlen = window
        self._samples: Dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=self._maxlen))
        self._counts: Dict[str, int] = defaultdict(int)
        self._totals: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def observe(self, name: str, value: float) -> None:
        observation = float(value)
        with self._lock:
            window = self._samples[name]
            window.append(observation)
            self._counts[name] += 1
            self._totals[name] += observation
        REQUEST_COUNTER.labels(operation=name).inc()
        LATENCY_HISTOGRAM.labels(operation=name).observe(observation)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            summary: Dict[str, Dict[str, float]] = {}
            for name, window in self._samples.items():
                if not window:
                    continue
                samples = list(window)
                ordered = sorted(samples)
                count_total = float(self._counts[name])
                window_count = float(len(samples))
                if len(ordered) == 1:
                    p50 = p95 = p99 = ordered[0]
                else:
                    def percentile(position: float) -> float:
                        index = position * (len(ordered) - 1)
                        lower = int(index)
                        upper = min(lower + 1, len(ordered) - 1)
                        weight = index - lower
                        return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)

                    p50 = percentile(0.50)
                    p95 = percentile(0.95)
                    p99 = percentile(0.99)

                average = float(self._totals[name] / self._counts[name]) if self._counts[name] else 0.0
                summary[name] = {
                    "count": count_total,
                    "window_count": window_count,
                    "p50": float(p50),
                    "p95": float(p95),
                    "p99": float(p99),
                    "avg": average,
                }
            return summary


class TraceEmitter:
    """Collect spans for a pseudo OpenTelemetry pipeline."""

    def __init__(self) -> None:
        self._spans: deque = deque(maxlen=256)
        self._lock = threading.Lock()

    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            self._spans.append(
                {
                    "name": name,
                    "attributes": attributes or {},
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._spans)


class ScorpioSync:
    """Periodic ticker that feeds Ouroboros/Tripolar rotation telemetry."""

    def __init__(self, tick_ms: float = 170.0, seed: str = "scorpio") -> None:
        self.tick_ms = tick_ms
        self.tick_interval = tick_ms / 1000.0
        self.seed = hashlib.sha256(seed.encode()).hexdigest()
        self.tick_no = 0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._active_snapshot: Dict[str, Any] = {}
        self._gate_window: deque = deque(maxlen=8)
        self._ouroboros_cycle = ["alpha", "beta", "gamma"]
        self._tripolar = ["north", "zenith", "abyss"]
        self._last_proof = hashlib.sha256(b"init").hexdigest()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.advance()
            time.sleep(self.tick_interval)

    def advance(self, *, active: Optional[Dict[str, Any]] = None, gate: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            if active:
                self._active_snapshot = active
            if gate:
                self._gate_window.append(gate)

            self.tick_no += 1
            ouroboros_phase = self._ouroboros_cycle[self.tick_no % len(self._ouroboros_cycle)]
            tripolar = self._tripolar[self.tick_no % len(self._tripolar)]

            payload = {
                "seed": self.seed,
                "tick_no": self.tick_no,
                "active": self._active_snapshot,
                "gate_window": list(self._gate_window),
                "phase": ouroboros_phase,
                "tripolar": tripolar,
            }
            self._last_proof = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            ouroboros_phase = self._ouroboros_cycle[self.tick_no % len(self._ouroboros_cycle)]
            tripolar = self._tripolar[self.tick_no % len(self._tripolar)]
            return {
                "tick_ms": self.tick_ms,
                "tick_no": self.tick_no,
                "tick_proof": self._last_proof,
                "ouroboros": {
                    "phase": ouroboros_phase,
                    "cycle": list(self._ouroboros_cycle),
                    "tripolar": tripolar,
                },
                "seed": self.seed,
            }


PROMETHEUS_REGISTRY = CollectorRegistry(auto_describe=True)
REQUEST_COUNTER = Counter(
    "mef_operation_requests_total",
    "Number of API operations observed",
    ["operation"],
    registry=PROMETHEUS_REGISTRY,
)
LATENCY_HISTOGRAM = Histogram(
    "mef_operation_latency_ms",
    "Latency distribution per operation in milliseconds",
    ["operation"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2000.0),
    registry=PROMETHEUS_REGISTRY,
)


metrics = OperationMetrics()
trace_emitter = TraceEmitter()
scorpio_sync = ScorpioSync()
_rate_limit_window = timedelta(seconds=5)
_rate_limit_threshold = 15
_rate_buckets: Dict[str, deque] = defaultdict(lambda: deque(maxlen=_rate_limit_threshold))


async def require_bearer(request: Request) -> str:
    if not AUTH_TOKEN_REQUIRED:
        return "anonymous"
    header = request.headers.get("Authorization")
    if not header or not header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = header.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid bearer token")

    bucket = _rate_buckets[token]
    now = datetime.utcnow()
    while bucket and now - bucket[0] > _rate_limit_window:
        bucket.popleft()
    if len(bucket) >= _rate_limit_threshold:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limit exceeded")
    bucket.append(now)
    return token


class SearchRequest(BaseModel):
    collection: str
    query_vector: List[float]
    top_k: int = Field(default=5, ge=1, le=100)
    membership_proof: bool = False
    pipeline_proof: bool = False
    provider: Optional[str] = None
    mode: Optional[str] = None
    ef_search: Optional[int] = Field(default=None, ge=1, le=10000)


class SearchResult(BaseModel):
    id: str
    score: float
    epoch: Optional[int]
    metadata: Optional[Dict[str, Any]] = None
    membership_proof: Optional[Dict[str, Any]] = None
    pipeline_proof: Optional[str] = None


class BatchProofRequest(BaseModel):
    members: List[Dict[str, str]]


class ProviderUpdate(BaseModel):
    provider: str


class CouplingSeedRequest(BaseModel):
    event: Dict[str, Any]


class CouplingSyncRequest(BaseModel):
    threshold: float


class SpiralNavRequest(BaseModel):
    theta_current: float
    candidates: List[float]
    params: Optional[Dict[str, float]] = None


class SpiralCondenseRequest(BaseModel):
    histories: List[List[float]]
    mode: str = "argmax_sumF"


class TicQueryRequest(BaseModel):
    vector: List[float]
    k: int = Field(..., gt=0)


class ZKInferRequest(BaseModel):
    x: Any


class VectorPayload(BaseModel):
    id: str
    vector: List[float]
    metadata: Optional[Dict[str, Any]] = None
    epoch: Optional[int] = None


class CollectionUpsertRequest(BaseModel):
    vectors: List[VectorPayload]
    epoch: Optional[int] = None
    provider: Optional[str] = None
    metric: Optional[str] = None


class BulkPointsRequest(BaseModel):
    collection: str
    points: List[VectorPayload]
    epoch: Optional[int] = None
    provider: Optional[str] = None
    metric: Optional[str] = None


@dataclass
class BulkIngestJob:
    """Track asynchronous bulk ingestion progress."""

    job_id: str
    status: str = "queued"
    total: int = 0
    inserted: int = 0
    batch_size: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    per_vector_ms: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "total": self.total,
            "inserted": self.inserted,
            "batch_size": self.batch_size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "per_vector_ms": self.per_vector_ms,
            "error": self.error,
        }


# In-memory registry for background ingestion jobs.
MAX_BULK_POINTS = 5000
RECOMMENDED_BULK_BATCH = min(
    int(os.getenv("MEF_RECOMMENDED_BULK_BATCH", "2000")),
    MAX_BULK_POINTS,
)
bulk_jobs: Dict[str, BulkIngestJob] = {}
bulk_jobs_lock = asyncio.Lock()


async def _store_job(job: BulkIngestJob) -> None:
    async with bulk_jobs_lock:
        bulk_jobs[job.job_id] = job


async def _update_job(job_id: str, **fields: Any) -> Optional[BulkIngestJob]:
    async with bulk_jobs_lock:
        job = bulk_jobs.get(job_id)
        if not job:
            return None
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = datetime.utcnow().isoformat() + "Z"
        return job


async def _get_job(job_id: str) -> Optional[BulkIngestJob]:
    async with bulk_jobs_lock:
        return bulk_jobs.get(job_id)


class IndexBuildRequest(BaseModel):
    collection: str

# Verzeichnisse erstellen
for p in (STORE_PATH, LEDGER_PATH, LOGS_PATH):
    p.mkdir(parents=True, exist_ok=True)

# Globale Instanzen
config = None
spiral = None
storage = None
por_validator = None
solve_coagula = None
tic_crystallizer = None
ledger = None
hdag = None
logger = None
index_manager = None
manifest_store = None
coupling_engine: Optional[SpiralCouplingEngine] = None
QUALITY_PROVIDER_CONFIG: Optional[str] = None


class GateFSM:
    """Minimal finite state machine snapshot for gate decisions."""

    def __init__(self) -> None:
        self.state = "idle"
        self.reasons: Dict[str, Any] = {
            "phi": None,
            "mci": None,
            "por": None,
            "deltaV": None,
            "t": None,
            "t'": None,
        }

    def update(self,
               status: str,
               snapshot: Dict[str, Any],
               tic: Dict[str, Any],
               lyapunov_series: Optional[List[float]] = None) -> None:
        """Update FSM state based on the most recent solve decision."""

        previous_timestamp = self.reasons.get("t'")
        now_ts = datetime.utcnow().isoformat() + "Z"

        delta_v: float
        if lyapunov_series:
            if len(lyapunov_series) >= 2:
                delta_v = float(lyapunov_series[-1] - lyapunov_series[-2])
            else:
                delta_v = -float(abs(lyapunov_series[-1]))
        else:
            delta_v = -0.0

        snapshot_metrics = snapshot.get("metrics", {})
        proof = tic.get("proof", {})

        self.state = "commit" if status == "ok" else "hold"
        self.reasons = {
            "phi": snapshot_metrics.get("resonance"),
            "mci": proof.get("mci"),
            "por": proof.get("por"),
            "deltaV": delta_v,
            "t": previous_timestamp,
            "t'": now_ts,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "reasons": dict(self.reasons),
        }


gate_fsm = GateFSM()
proof_registry = ProofRegistry()
delta_pi_violations = 0
mode_state: Dict[str, Any] = {
    "mode": "idle",
    "tick_ms": 0.0,
    "tick_no": 0,
    "active_contingent": None,
    "tick_proof": None,
}


def _resolved_quality_provider() -> Optional[str]:
    if QUALITY_PROVIDER_ENV:
        return QUALITY_PROVIDER_ENV
    return QUALITY_PROVIDER_CONFIG


def _normalise_numeric_mapping(payload: Mapping[str, Any]) -> Dict[str, float]:
    canonical: Dict[str, float] = {}
    for key, value in payload.items():
        if isinstance(value, (int, float)):
            canonical[key] = float(value)
    return canonical


def _ensure_quality_collection() -> None:
    if index_manager is None:
        return

    collection_name = QUALITY_COLLECTION
    state = index_manager.get_collection_state(collection_name)

    providers_catalogue = index_manager.list_providers()
    available_provider = next(iter(providers_catalogue.keys()), None)

    provider_hint = _resolved_quality_provider()
    target_provider = provider_hint or state.indexes.get("provider") or available_provider
    if target_provider:
        provider_token = str(target_provider).lower()
        if state.indexes.get("provider") != provider_token:
            try:
                index_manager.set_collection_provider(collection_name, provider_token)
                state = index_manager.get_collection_state(collection_name)
            except KeyError:
                if available_provider and available_provider != provider_token:
                    index_manager.set_collection_provider(collection_name, available_provider)
                    state = index_manager.get_collection_state(collection_name)

    provider_snapshot = state.indexes.get("provider") or provider_hint or available_provider
    if provider_snapshot:
        index_manager.collection_providers.setdefault(
            collection_name,
            str(provider_snapshot).lower(),
        )

    metric = QUALITY_METRIC
    if metric and state.indexes.get("metric") != metric:
        state.indexes["metric"] = metric


def _upsert_quality_vector(
    snapshot: Mapping[str, Any],
    tic: Mapping[str, Any],
    *,
    snapshot_id: str,
    status: str,
    convergence: Mapping[str, Any],
) -> None:
    if index_manager is None:
        return

    _ensure_quality_collection()

    vector_raw = tic.get("fixpoint")
    if not isinstance(vector_raw, (list, tuple)):
        return

    vector = [float(value) for value in vector_raw]
    if not vector:
        return

    payload = snapshot.get("payload") if isinstance(snapshot, Mapping) else {}
    data_payload: Mapping[str, Any]
    if isinstance(payload, Mapping) and isinstance(payload.get("data"), Mapping):
        data_payload = payload["data"]  # type: ignore[index]
    else:
        data_payload = {}

    meta_payload: Mapping[str, Any]
    if isinstance(data_payload.get("meta"), Mapping):
        meta_payload = data_payload["meta"]  # type: ignore[index]
    else:
        meta_payload = {}

    dataset_id = (
        meta_payload.get("dataset_id")
        or data_payload.get("id")
        or snapshot_id
        or tic.get("tic_id")
    )
    vector_id = str(dataset_id or tic.get("tic_id") or snapshot_id)

    source = meta_payload.get("source") or data_payload.get("source") or "solve"
    text = data_payload.get("text") if isinstance(data_payload.get("text"), str) else None
    attributes = (
        dict(data_payload.get("attributes"))
        if isinstance(data_payload.get("attributes"), Mapping)
        else None
    )

    metadata: Dict[str, Any] = {
        "snapshot_id": snapshot_id,
        "tic_id": tic.get("tic_id"),
        "status": status,
        "collection": QUALITY_COLLECTION,
        "source": str(source),
    }

    if dataset_id:
        metadata["dataset_id"] = str(dataset_id)
    if text:
        metadata["text"] = text
    if attributes:
        metadata["attributes"] = attributes

    invariants = tic.get("invariants")
    if isinstance(invariants, Mapping):
        metadata["invariants"] = _normalise_numeric_mapping(invariants)

    sigma_bar = tic.get("sigma_bar")
    if isinstance(sigma_bar, Mapping):
        metadata["sigma_bar"] = _normalise_numeric_mapping(sigma_bar)

    proof = tic.get("proof")
    if isinstance(proof, Mapping):
        metadata["proof"] = {
            key: proof[key]
            for key in ("por", "pi_gap", "mci")
            if key in proof and proof[key] is not None
        }

    metadata = {key: value for key, value in metadata.items() if value is not None}

    epoch_value = int(convergence.get("iterations", 0) or 0)

    indexes: Dict[str, Any] = {}
    if QUALITY_METRIC:
        indexes["metric"] = QUALITY_METRIC
    provider_hint = _resolved_quality_provider()
    if provider_hint:
        indexes["provider"] = provider_hint

    index_manager.upsert_vectors(
        QUALITY_COLLECTION,
        [
            {
                "id": vector_id,
                "vector": vector,
                "metadata": metadata,
                "epoch": epoch_value,
            }
        ],
        epoch=epoch_value,
        indexes=indexes or None,
    )

    proof_registry.refresh_from_collections(index_manager.collections)

    try:
        logger.log_event(
            "QUALITY_VECTOR_UPSERT",
            "API",
            {
                "collection": QUALITY_COLLECTION,
                "vector_id": vector_id,
                "epoch": epoch_value,
                "status": status,
                "provider": index_manager.collection_providers.get(QUALITY_COLLECTION),
            },
        )
    except Exception:
        pass

def load_config() -> Dict[str, Any]:
    """Lade Konfiguration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f)
    
    # Standard-Konfiguration
    return {
        "seed": "MEF_SEED_42",
        "spiral": {
            "r": 1.0, "a": 0.05, "b": 0.2, "c": 0.2, "k": 2, "step": 0.01
        },
        "solvecoagula": {
            "lambda": 0.8, "eps": 1e-6, "max_iter": 1000,
            "operators": {
                "dk": {"alpha1": 0.05, "alpha2": -0.03},
                "sw": {"tau0": 0.5, "beta": 0.1, "schedule": "cosine"},
                "pi": {"canon": "lexicographic", "tol": 1e-6},
                "wt": {"gamma": 0.1, "levels": ["micro", "meso", "macro"]}
            }
        },
        "gate": {
            "por_delta": 0.02, "phi_star": 0.6, "mci_min": 0.9
        },
        "ledger": {"path": str(LEDGER_PATH)},
        "store": {"path": str(STORE_PATH)},
        "vector_store": {
            "path": str(STORE_PATH / "vector_db"),
            "persistence": {
                "provider": None,
                "bucket": None,
                "prefix": None,
            },
        },
    }

def initialize_components():
    """Initialisiere alle Komponenten."""
    global config, spiral, storage, por_validator, solve_coagula
    global tic_crystallizer, ledger, hdag, logger, index_manager, manifest_store
    global scorpio_sync, coupling_engine

    config = load_config()

    global QUALITY_PROVIDER_CONFIG
    provider_from_config: Optional[str] = None
    index_settings = config.get("index", {}) if isinstance(config, dict) else {}
    if isinstance(index_settings, Mapping):
        candidate = index_settings.get("provider")
        if isinstance(candidate, str) and candidate.strip():
            provider_from_config = candidate.strip().lower()
    if not provider_from_config:
        vector_store_section = config.get("vector_store", {}) if isinstance(config, dict) else {}
        if isinstance(vector_store_section, Mapping):
            candidate = vector_store_section.get("provider")
            if isinstance(candidate, str) and candidate.strip():
                provider_from_config = candidate.strip().lower()
    QUALITY_PROVIDER_CONFIG = provider_from_config

    seed_material = str(config.get("seed", "MEF_SEED_42"))
    seed_digest = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    random.seed(seed_digest)
    np.random.seed(seed_digest & 0xFFFFFFFF)

    spiral = SpiralSnapshot(config['spiral'], str(STORE_PATH))
    storage = SpiralStorage(str(STORE_PATH))
    por_validator = ProofOfResonance(config)
    solve_coagula = SolveCoagula(config['solvecoagula'])
    tic_crystallizer = TICCrystallizer(config, str(STORE_PATH))
    ledger = MEFLedger(str(LEDGER_PATH))
    hdag = HDAG(str(STORE_PATH))
    logger = MEFAuditLogger(str(LOGS_PATH))

    vector_store_config = config.get("vector_store", {})
    vector_store_path = Path(vector_store_config.get("path") or (STORE_PATH / "vector_db"))
    persistence_config = vector_store_config.get("persistence")
    manifest_store = ManifestStore(
        vector_store_path,
        manifest_data=vector_store_config.get("manifest"),
        persistence_config=persistence_config,
    )
    index_manager = IndexManager(vector_store_path)
    _ensure_quality_collection()
    proof_registry.refresh_from_collections(index_manager.collections)

    scorpio_sync = ScorpioSync(
        tick_ms=float(config.get("scorpio_sync", {}).get("tick_ms", 170.0)),
        seed=str(config.get("seed", "scorpio")),
    )
    coupling_engine = SpiralCouplingEngine(STORE_PATH / "coupling")

    try:
        tic_index = getattr(storage, "index", {}).get("tics", {})
        for tic_meta in sorted(tic_index.values(), key=lambda entry: entry.get("id")):
            tic_id = tic_meta.get("id")
            if not tic_id:
                continue
            tic_payload = storage.retrieve_tic(tic_id)
            if not tic_payload:
                continue
            try:
                coupling_engine.register_tic(tic_payload)
            except Exception:
                continue
    except Exception:
        pass

@app.on_event("startup")
async def startup_event():
    """System-Initialisierung beim Start."""
    initialize_components()
    print(f"MEF-Core SPEC-002 API gestartet")
    print(f"Seed: {config['seed']}")
    print(f"Store: {STORE_PATH}")
    print(f"Ledger: {LEDGER_PATH}")
    scorpio_sync.start()

# SPEC-002 Endpunkte

@app.get("/ping")
async def ping():
    """Basic liveness probe used for quick connectivity checks."""
    return {"status": "alive"}


@app.get("/healthz")
async def healthz():
    """Lightweight health endpoint used by Docker/CI probes."""

    return {
        "status": "up",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "components": {
            "ledger": str(LEDGER_PATH),
            "store": str(STORE_PATH),
            "logs": str(LOGS_PATH),
        },
    }


@app.get("/metrics")
async def prometheus_metrics():
    """Expose Prometheus-compatible metrics for scraping."""

    try:
        payload = generate_latest(PROMETHEUS_REGISTRY)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=500, detail=f"failed to render metrics: {exc}") from exc

    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


@app.get("/readyz")
async def readyz():
    """Readiness probe exposing component state once initialisation completes."""

    commit_snapshot: Dict[str, Any]
    try:
        commit_snapshot = proof_registry.get_commit_snapshot()
    except Exception as exc:  # pragma: no cover - defensive guard
        commit_snapshot = {"error": str(exc)}

    collections_summary: List[Dict[str, Any]] = []
    try:
        if "index_manager" in globals() and index_manager is not None:
            for name in sorted(index_manager.collections):
                state = index_manager.collections[name]
                collections_summary.append(
                    {
                        "name": name,
                        "vectors": len(state.vectors),
                        "provider": index_manager.collection_providers.get(name),
                    }
                )
    except Exception as exc:  # pragma: no cover - defensive guard
        collections_summary = [{"error": str(exc)}]

    scorpio_snapshot: Dict[str, Any] = {}
    try:
        if "scorpio_sync" in globals() and scorpio_sync is not None:
            scorpio_snapshot = scorpio_sync.snapshot()
    except Exception as exc:  # pragma: no cover - defensive guard
        scorpio_snapshot = {"error": str(exc)}

    readiness_components = {
        "commit": commit_snapshot,
        "collections": collections_summary,
        "scorpio": scorpio_snapshot,
        "manifest_store": {
            "path": str(manifest_store.base_path) if "manifest_store" in globals() else None,
        },
    }

    return {
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "components": readiness_components,
    }

@app.get("/collections")
async def list_collections(token: str = Depends(require_bearer)):
    """Return a deterministic summary of all known collections."""

    manifest_snapshot: Dict[str, Any] = {}
    if "manifest_store" in globals() and manifest_store is not None:
        try:
            manifest_snapshot = manifest_store.get_manifest().to_dict()
        except Exception as exc:  # pragma: no cover - defensive guard
            manifest_snapshot = {"error": str(exc)}

    manifest_collections: Dict[str, Any] = {}
    if isinstance(manifest_snapshot, dict):
        manifest_collections = manifest_snapshot.get("collections", {}) or {}

    collections_payload: List[Dict[str, Any]] = []
    if "index_manager" in globals() and index_manager is not None:
        for name in sorted(index_manager.collections.keys()):
            state = index_manager.collections[name]
            provider = (
                state.indexes.get("provider")
                or index_manager.collection_providers.get(name)
            )
            metric = state.indexes.get("metric")
            proof_version = int(state.indexes.get("proof_version", 0) or 0)
            manifest_entry = {}
            if isinstance(manifest_collections, dict):
                manifest_entry = dict(manifest_collections.get(name, {}))

            index_status = index_manager.get_index_status(name)
            collections_payload.append(
                {
                    "name": name,
                    "vector_count": len(state.vectors),
                    "provider": provider,
                    "metric": metric,
                    "proof_version": proof_version,
                    "indexes": dict(state.indexes),
                    "manifest": manifest_entry,
                    "index_status": index_status,
                }
            )

    return {
        "collections": collections_payload,
        "manifest": manifest_snapshot,
    }


@app.post("/acquisition")
async def acquisition(payload: dict):
    """
    SPEC-002: Acquisition-Endpunkt.
    Nimmt payload, normalisiert, erzeugt SpiralSnapshot, speichert, liefert snapshot_id.
    """
    try:
        # Normalisiere Payload (SPEC-002)
        normalized = normalize_payload(payload)
        
        # Erzeuge Spiral Snapshot
        snapshot = spiral.create_snapshot(
            data=normalized,
            seed=config['seed'],
            phase=None  # Auto-berechnet
        )
        
        # Speichere Snapshot
        file_path = spiral.save_snapshot(snapshot)
        storage.store_snapshot(snapshot)
        
        # Log Event
        logger.log_event(
            "ACQUISITION",
            "API",
            {
                "snapshot_id": snapshot['id'],
                "phase": snapshot['phase'],
                "por": snapshot['metrics']['por']
            }
        )
        
        return {
            "snapshot_id": snapshot['id'],
            "phase": snapshot['phase'],
            "por": snapshot['metrics']['por'],
            "stored": str(file_path)
        }
        
    except Exception as e:
        logger.log_error("API", e, {"endpoint": "/acquisition"})
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search_vectors(
    request: SearchRequest,
    response: Response,
    token: str = Depends(require_bearer),
):
    start = time.perf_counter()
    proof_registry.refresh_from_collections(index_manager.collections)

    results = index_manager.search_vectors(
        request.collection,
        request.query_vector,
        top_k=request.top_k,
        provider=request.provider,
        mode=request.mode,
        ef_search=request.ef_search,
    )

    plan_snapshot = index_manager.last_search_plan()
    provider_used_meta: Dict[str, Any] = {}
    provider_display: Optional[str] = None
    provider_name_used: Optional[str] = None
    provider_version_used: Optional[str] = None
    if isinstance(plan_snapshot, dict):
        provider_used_meta = plan_snapshot.get("provider_used") or {}
        provider_name_used = provider_used_meta.get("name")
        provider_version_used = provider_used_meta.get("version")
        if provider_name_used:
            provider_display = provider_name_used
            if provider_version_used:
                provider_display = f"{provider_name_used}@{provider_version_used}"
            response.headers["X-Provider-Used"] = provider_display
            plan_snapshot.setdefault("provider_display", provider_display)
    else:
        plan_snapshot = {}

    commit_snapshot = proof_registry.get_commit_snapshot()
    index_status = index_manager.get_index_status(request.collection)
    response_results: List[SearchResult] = []

    provider_for_proof = (
        provider_used_meta.get("name")
        or request.provider
        or index_manager.collection_providers.get(request.collection)
    )

    if provider_display is None and provider_for_proof:
        provider_display = provider_for_proof
        response.headers.setdefault("X-Provider-Used", provider_display)
    if provider_display and isinstance(plan_snapshot, dict):
        plan_snapshot.setdefault("provider_display", provider_display)

    index_params: Dict[str, Any] = {}
    if isinstance(plan_snapshot, dict):
        plan_params = plan_snapshot.get("params")
        if isinstance(plan_params, dict):
            index_params.update(plan_params)
    status_params = index_status.get("params") if isinstance(index_status, dict) else {}
    if isinstance(status_params, dict):
        for key, value in status_params.items():
            index_params.setdefault(key, value)
    if request.ef_search is not None:
        index_params.setdefault("efSearchRequest", int(request.ef_search))
    if provider_for_proof:
        index_params.setdefault("provider", provider_for_proof)

    for entry in results:
        result_payload = SearchResult(
            id=entry["id"],
            score=float(entry["score"]),
            epoch=entry.get("epoch"),
            metadata=entry.get("metadata"),
        )

        if request.membership_proof:
            proof = proof_registry.get_membership_proof(request.collection, entry["id"])
            if proof:
                result_payload.membership_proof = {
                    "collection": proof.collection,
                    "vector_id": proof.vector_id,
                    "leaf": proof.leaf,
                    "siblings": proof.siblings,
                    "collection_root": proof.collection_root,
                    "commit_root": proof.commit_root,
                }

        if request.pipeline_proof:
            pipeline_material = {
                "collection": request.collection,
                "query": request.query_vector,
                "top_k": request.top_k,
                "provider": provider_for_proof,
                "commit_root": commit_snapshot["commit_root"],
                "result_id": entry["id"],
            }
            result_payload.pipeline_proof = hashlib.sha256(
                json.dumps(pipeline_material, sort_keys=True).encode()
            ).hexdigest()

        response_results.append(result_payload)

    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("search", duration_ms)
    if plan_snapshot:
        SEARCH_LOGGER.info("search plan: %s", json.dumps(plan_snapshot, sort_keys=True))
        try:
            logger.log_event("SEARCH_PLAN", "API", plan_snapshot)
        except Exception:  # pragma: no cover - audit logger resilience
            pass
    trace_emitter.span(
        "search",
        {
            "collection": request.collection,
            "top_k": request.top_k,
            "provider": request.provider,
            "results": len(response_results),
            "duration_ms": round(duration_ms, 6),
            "plan": plan_snapshot,
        },
    )

    proof_context = {
        "provider": provider_for_proof,
        "provider_version": provider_version_used,
        "proof_version": index_status.get("proof_version") if isinstance(index_status, dict) else None,
        "index_params": index_params,
    }

    return {
        "commit": commit_snapshot,
        "provider_used": provider_display,
        "proof_context": proof_context,
        "results": [result.dict(exclude_none=True) for result in response_results],
    }


def _require_coupling_engine() -> SpiralCouplingEngine:
    if coupling_engine is None:
        raise HTTPException(status_code=503, detail="coupling engine not initialised")
    return coupling_engine


@app.post("/coupling/seed")
async def coupling_seed(
    request: CouplingSeedRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    start = time.perf_counter()
    try:
        result = engine.inject_seed(request.event)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("coupling_seed", duration_ms)
    trace_emitter.span(
        "coupling_seed",
        {
            "duration_ms": round(duration_ms, 6),
            "has_event": bool(request.event),
        },
    )
    return result


@app.post("/coupling/sync")
async def coupling_sync(
    request: CouplingSyncRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    start = time.perf_counter()
    result = engine.sync_hdag(float(request.threshold))
    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("coupling_sync", duration_ms)
    trace_emitter.span(
        "coupling_sync",
        {
            "duration_ms": round(duration_ms, 6),
            "threshold": float(request.threshold),
            "edges_added": result.get("edges_added"),
        },
    )
    return result


@app.post("/spiral/nav")
async def spiral_nav(
    request: SpiralNavRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    start = time.perf_counter()
    try:
        result = engine.navigate_spiral(
            float(request.theta_current),
            [float(x) for x in request.candidates],
            params=request.params,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("spiral_nav", duration_ms)
    trace_emitter.span(
        "spiral_nav",
        {
            "duration_ms": round(duration_ms, 6),
            "candidates": len(request.candidates),
            "theta_next": result["theta_next"],
            "score": result["score"],
        },
    )
    return result


@app.post("/spiral/condense")
async def spiral_condense(
    request: SpiralCondenseRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    start = time.perf_counter()
    try:
        result = engine.condense_histories(request.histories, mode=request.mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    delta_pi = result.get("invariants", {}).get("delta_pi", 0.0)
    if delta_pi is not None and float(delta_pi) > engine.eps_pi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ΔPI {float(delta_pi):.6f} exceeds EPS_PI {engine.eps_pi:.6f}",
        )

    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("spiral_condense", duration_ms)
    trace_emitter.span(
        "spiral_condense",
        {
            "duration_ms": round(duration_ms, 6),
            "mode": request.mode,
            "delta_pi": delta_pi,
            "tic_id": result.get("tic_id"),
        },
    )
    return result


@app.post("/tic/query")
async def tic_query(
    request: TicQueryRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    start = time.perf_counter()
    try:
        results = engine.query_tics(request.vector, request.k)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("tic_query", duration_ms)
    trace_emitter.span(
        "tic_query",
        {
            "duration_ms": round(duration_ms, 6),
            "k": request.k,
            "results": len(results),
        },
    )
    return results


@app.post("/zk/infer")
async def zk_infer(
    request: ZKInferRequest,
    token: str = Depends(require_bearer),
):
    engine = _require_coupling_engine()
    result = engine.zk_infer(request.x)
    trace_emitter.span("zk_infer", {"lzk": result["lzk"]})
    return result


@app.get("/commit")
async def get_commit_metadata(token: str = Depends(require_bearer)):
    proof_registry.refresh_from_collections(index_manager.collections)
    snapshot = proof_registry.get_commit_snapshot()
    trace_emitter.span("commit", snapshot)
    return snapshot


@app.post("/commit/rotate")
async def rotate_commit_secret(
    kid: Optional[str] = None,
    secret: Optional[str] = None,
    token: str = Depends(require_bearer),
):
    if not kid and not secret:
        raise HTTPException(status_code=400, detail="kid or secret required for rotation")
    snapshot = proof_registry.rotate_secret(kid=kid, secret=secret)
    trace_emitter.span("commit.rotate", snapshot)
    return snapshot


def _resolve_membership_proof(identifier: str) -> Dict[str, Any]:
    if ":" not in identifier:
        raise HTTPException(status_code=400, detail="identifier must be collection:vector_id")
    collection, vector_id = identifier.split(":", 1)
    proof_registry.refresh_from_collections(index_manager.collections)
    proof = proof_registry.get_membership_proof(collection, vector_id)
    if not proof:
        raise HTTPException(status_code=404, detail="membership proof not found")
    return {
        "collection": proof.collection,
        "vector_id": proof.vector_id,
        "leaf": proof.leaf,
        "siblings": proof.siblings,
        "collection_root": proof.collection_root,
        "commit_root": proof.commit_root,
        "kid": proof_registry.kid,
        "signature": proof_registry.signature,
    }


@app.get("/proof/{identifier}")
async def get_membership_proof(identifier: str, token: str = Depends(require_bearer)):
    payload = _resolve_membership_proof(identifier)
    trace_emitter.span("proof", payload)
    return payload


@app.get("/proof/{id}")
async def get_membership_proof_by_id(id: str, token: str = Depends(require_bearer)):
    payload = _resolve_membership_proof(id)
    trace_emitter.span("proof", payload)
    return payload


@app.post("/proof/batch")
async def get_batch_proofs(request: BatchProofRequest, token: str = Depends(require_bearer)):
    members = []
    for entry in request.members:
        collection = entry.get("collection")
        vector_id = entry.get("vector_id")
        if not collection or not vector_id:
            raise HTTPException(status_code=400, detail="each member requires collection and vector_id")
        members.append((collection, vector_id))

    proof_registry.refresh_from_collections(index_manager.collections)
    proofs = proof_registry.batch_membership_proofs(members)
    return {
        "commit": proof_registry.get_commit_snapshot(),
        "proofs": [
            {
                "collection": proof.collection,
                "vector_id": proof.vector_id,
                "leaf": proof.leaf,
                "siblings": proof.siblings,
                "collection_root": proof.collection_root,
                "commit_root": proof.commit_root,
            }
            for proof in proofs
        ],
    }


@app.get("/index/providers")
async def list_index_providers(token: str = Depends(require_bearer)):
    catalogue = index_manager.list_providers()
    trace_emitter.span("index.providers", catalogue)
    return catalogue


@app.patch("/collections/{name}/provider")
async def update_collection_provider(
    name: str,
    payload: ProviderUpdate,
    token: str = Depends(require_bearer),
):
    try:
        status_payload = index_manager.set_collection_provider(name, payload.provider)
    except KeyError as exc:
        message = str(exc)
        if "unknown provider" in message:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc

    proof_registry.refresh_from_collections(index_manager.collections)

    try:
        logger.log_event(
            "PROVIDER_UPDATE",
            "API",
            {
                "collection": name,
                "provider": payload.provider,
                "previous": status_payload.get("previous_provider"),
                "proof_version": status_payload.get("proof_version"),
            },
        )
    except Exception:  # pragma: no cover - audit resilience
        pass

    trace_emitter.span(
        "index.provider.update",
        {
            "collection": name,
            "provider": payload.provider,
            "proof_version": status_payload.get("proof_version"),
        },
    )
    return status_payload


@app.post("/collections/{name}/upsert")
async def upsert_collection_vectors(
    name: str,
    request: CollectionUpsertRequest,
    token: str = Depends(require_bearer),
):
    start = time.perf_counter()

    epoch = request.epoch if request.epoch is not None else 1
    state = index_manager.get_collection_state(name)
    current_provider = state.indexes.get("provider")
    requested_provider = request.provider
    if requested_provider and current_provider and requested_provider != current_provider:
        allow_override = os.getenv("ALLOW_PROVIDER_OVERRIDE_IN_UPSERT", "false").lower() == "true"
        if not allow_override:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"collection {name} provider mismatch; use PATCH /collections/{{name}}/provider "
                    "to change the active provider"
                ),
            )
        index_manager.set_collection_provider(name, requested_provider)
        state = index_manager.get_collection_state(name)

    if not request.vectors:
        duration_ms = (time.perf_counter() - start) * 1000.0
        metrics.observe("index_upsert", duration_ms)
        trace_emitter.span(
            "index.upsert",
            {
                "collection": name,
                "upserted": 0,
                "duration_ms": round(duration_ms, 6),
            },
        )
        return {
            "collection": name,
            "upserted": 0,
            "total_vectors": len(state.vectors),
            "provider": index_manager.collection_providers.get(name)
            or state.indexes.get("provider"),
            "metric": state.indexes.get("metric"),
        }

    records: List[Dict[str, Any]] = []
    for vector in request.vectors:
        record_epoch = vector.epoch if vector.epoch is not None else epoch
        metadata = json.loads(json.dumps(vector.metadata or {}))
        records.append(
            {
                "id": vector.id,
                "vector": list(vector.vector),
                "metadata": metadata,
                "epoch": record_epoch,
            }
        )

    indexes: Dict[str, Any] = {}
    if request.provider:
        indexes["provider"] = request.provider
    if request.metric:
        indexes["metric"] = request.metric.lower()

    state = index_manager.upsert_vectors(
        name, records, epoch=epoch, indexes=indexes or None
    )
    proof_registry.refresh_from_collections(index_manager.collections)

    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("index_upsert", duration_ms)
    trace_emitter.span(
        "index.upsert",
        {
            "collection": name,
            "upserted": len(records),
            "duration_ms": round(duration_ms, 6),
        },
    )

    return {
        "collection": name,
        "upserted": len(records),
        "total_vectors": len(state.vectors),
        "provider": index_manager.collection_providers.get(name)
        or state.indexes.get("provider"),
        "metric": state.indexes.get("metric"),
    }


async def _run_bulk_job(job_id: str, payload: BulkPointsRequest, token: str) -> None:
    await _update_job(job_id, status="running", batch_size=len(payload.points))
    start = time.perf_counter()
    try:
        result = await upsert_collection_vectors(
            payload.collection,
            CollectionUpsertRequest(
                vectors=payload.points,
                epoch=payload.epoch,
                provider=payload.provider,
                metric=payload.metric,
            ),
            token,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        per_vector_ms = duration_ms / max(1, len(payload.points))
        await _update_job(
            job_id,
            status="completed",
            inserted=int(result.get("upserted", len(payload.points))),
            completed_at=datetime.utcnow().isoformat() + "Z",
            duration_ms=duration_ms,
            per_vector_ms=per_vector_ms,
        )
        metrics.observe("index_upsert_per_vector", per_vector_ms)
        try:
            logger.log_event(
                "BULK_JOB_COMPLETED",
                "API",
                {
                    "job_id": job_id,
                    "collection": payload.collection,
                    "upserted": result.get("upserted"),
                    "duration_ms": round(duration_ms, 6),
                    "per_vector_ms": round(per_vector_ms, 6),
                },
            )
        except Exception:  # pragma: no cover - audit resilience
            pass
    except Exception as exc:  # pragma: no cover - surfaced via job status
        await _update_job(
            job_id,
            status="failed",
            error=str(exc),
            completed_at=datetime.utcnow().isoformat() + "Z",
        )
        try:
            logger.log_error(
                "API",
                exc,
                {"endpoint": "/points/bulk", "job_id": job_id, "collection": payload.collection},
            )
        except Exception:
            pass


@app.post("/points/bulk", status_code=status.HTTP_202_ACCEPTED)
async def bulk_upsert_points(
    request: BulkPointsRequest,
    response: Response,
    token: str = Depends(require_bearer),
):
    total_points = len(request.points)
    if total_points > MAX_BULK_POINTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"maximum batch size {MAX_BULK_POINTS} exceeded",
        )

    job_id = uuid.uuid4().hex
    job = BulkIngestJob(
        job_id=job_id,
        total=total_points,
        batch_size=total_points,
    )
    await _store_job(job)

    response.headers["X-Recommended-Batch-Size"] = str(RECOMMENDED_BULK_BATCH)
    asyncio.create_task(_run_bulk_job(job_id, request.model_copy(deep=True), token))
    return {"job_id": job_id, "status": job.status, "total": total_points}


@app.get("/points/bulk/{job_id}")
async def bulk_job_status(job_id: str, token: str = Depends(require_bearer)):
    job = await _get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="bulk job not found")
    return job.to_dict()


@app.post("/index/build")
async def build_index(request: IndexBuildRequest, token: str = Depends(require_bearer)):
    start = time.perf_counter()
    try:
        status_payload = index_manager.build_index(request.collection)
    except KeyError as exc:  # pragma: no cover - sanity guard
        raise HTTPException(status_code=404, detail=f"collection {request.collection} not found") from exc

    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("index_build", duration_ms)
    trace_emitter.span(
        "index.build",
        {
            "collection": request.collection,
            "duration_ms": round(duration_ms, 6),
            "points_indexed": status_payload.get("points_indexed"),
        },
    )
    return status_payload


@app.get("/index/status")
async def index_status(collection: str = Query(...), token: str = Depends(require_bearer)):
    status_payload = index_manager.get_index_status(collection)
    trace_emitter.span(
        "index.status",
        {
            "collection": collection,
            "ready": status_payload.get("ready"),
            "points_indexed": status_payload.get("points_indexed"),
        },
    )
    return status_payload


@app.get("/debug/search-plan")
async def debug_search_plan(token: str = Depends(require_bearer)):
    plan = index_manager.last_search_plan()
    if not plan:
        raise HTTPException(status_code=404, detail="no search plan recorded")
    return plan


@app.get("/collections/{name}/vectors")
async def list_collection_vectors(
    name: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=100000),
    token: str = Depends(require_bearer),
):
    state = index_manager.collections.get(name)
    if state is None:
        raise HTTPException(status_code=404, detail=f"collection {name} not found")

    start = time.perf_counter()
    ordered_ids = sorted(state.vectors.keys())
    total = len(ordered_ids)
    slice_ids = ordered_ids[offset : offset + limit]

    vectors = []
    for vector_id in slice_ids:
        payload = state.vectors[vector_id]
        vectors.append(
            {
                "id": vector_id,
                "vector": list(payload.get("vector") or []),
                "metadata": payload.get("metadata"),
                "epoch": payload.get("epoch"),
            }
        )

    duration_ms = (time.perf_counter() - start) * 1000.0
    metrics.observe("index_list", duration_ms)
    trace_emitter.span(
        "index.vectors",
        {
            "collection": name,
            "returned": len(vectors),
            "offset": offset,
            "limit": limit,
        },
    )

    return {
        "collection": name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "provider": index_manager.collection_providers.get(name)
        or state.indexes.get("provider"),
        "metric": state.indexes.get("metric") or "cosine",
        "vectors": vectors,
    }

@app.post("/solve")
async def solve(
    snapshot_id: str,
    request: Request,
    token: str = Depends(require_bearer),
):
    """
    SPEC-002: Solve-Endpunkt.
    Lädt Snapshot, berechnet (v*, steps), erstellt TIC, PoR/PI/MCI-Checks.
    """
    try:
        start_time = time.perf_counter()
        mode_state.update({
            "mode": "solve",
            "active_contingent": {"snapshot_id": snapshot_id},
        })

        # Lade Snapshot
        snapshot = storage.retrieve_snapshot(snapshot_id)
        if not snapshot:
            mode_state.update({
                "mode": "error",
                "active_contingent": {"snapshot_id": snapshot_id},
            })
            raise HTTPException(status_code=404, detail="Snapshot not found")

        golden_header = request.headers.get("X-Golden-Run", "").lower() == "true"
        golden_env = os.getenv("GOLDEN_POR_OVERRIDE", "false").lower() == "true"
        por_override_active = golden_header or golden_env

        # PoR-Check VOR Solve (SPEC-002 Punkt 7)
        if snapshot['metrics']['por'] != 'valid':
            if por_override_active:
                logger.log_event(
                    "POR_OVERRIDE_FIRE",
                    "API",
                    {"snapshot_id": snapshot_id, "override": "fire"},
                    severity="INFO",
                )
                snapshot['metrics']['por'] = 'valid'
            else:
                # HOLD: kein Commit bei invalid PoR
                logger.log_event(
                    "POR_INVALID_HOLD",
                    "API",
                    {"snapshot_id": snapshot_id},
                    severity="WARNING"
                )
                raise HTTPException(status_code=400, detail="HOLD: PoR invalid")
        
        # Solve-Coagula
        coordinates = np.array(snapshot['coordinates'])
        v_star, convergence_info = solve_coagula.iterate_to_fixpoint(
            coordinates,
            track_convergence=True
        )
        
        # Prüfe Konvergenz
        if convergence_info['iterations'] > 1000:
            logger.log_event(
                "SOLVE_MAX_ITER",
                "API",
                {"snapshot_id": snapshot_id, "iterations": convergence_info['iterations']},
                severity="WARNING"
            )
        
        # Erstelle TIC
        tic = tic_crystallizer.create_tic(
            fixpoint=v_star,
            snapshot_id=snapshot['id'],
            seed=snapshot['seed'],
            convergence_info=convergence_info,
            snapshot_data=snapshot
        )

        delta_pi = float(tic['invariants'].get('delta_pi', 0.0))
        if delta_pi > EPS_PI_DEFAULT:
            global delta_pi_violations
            delta_pi_violations += 1
            logger.log_event(
                "DELTA_PI_VIOLATION",
                "API",
                {
                    "snapshot_id": snapshot_id,
                    "tic_id": tic['tic_id'],
                    "delta_pi": delta_pi,
                    "eps_pi": EPS_PI_DEFAULT,
                },
                severity="ERROR",
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"ΔPI {delta_pi:.6f} exceeds EPS_PI {EPS_PI_DEFAULT:.6f}",
            )

        # Speichere TIC
        tic_file = tic_crystallizer.save_tic(tic)
        storage.store_tic(tic)

        if 'coupling_engine' in globals() and coupling_engine is not None:
            try:
                coupling_engine.register_tic(tic)
            except Exception as exc:
                logger.log_event(
                    "COUPLING_REGISTER_TIC_FAILED",
                    "API",
                    {"snapshot_id": snapshot_id, "tic_id": tic['tic_id'], "error": str(exc)},
                    severity="WARNING",
                )

        mode_state.setdefault("active_contingent", {})
        active_contingent = mode_state["active_contingent"] or {}
        active_contingent.update({
            "snapshot_id": snapshot_id,
            "tic_id": tic['tic_id'],
        })
        mode_state["active_contingent"] = active_contingent

        # HDAG Update (SPEC-002 Punkt 6)
        if 'prev_snapshot' in snapshot:
            prev_snapshot = storage.retrieve_snapshot(snapshot['prev_snapshot'])
            if prev_snapshot:
                edge_id = hdag.update_hdag(prev_snapshot, snapshot)
                if not edge_id:
                    logger.log_event(
                        "HDAG_CYCLE_HOLD",
                        "API",
                        {"snapshot_id": snapshot_id},
                        severity="WARNING"
                    )
        
        # Log Event
        logger.log_event(
            "SOLVE_COMPLETE",
            "API",
            {
                "snapshot_id": snapshot_id,
                "tic_id": tic['tic_id'],
                "steps": convergence_info['iterations'],
                "converged": convergence_info['converged']
            }
        )
        
        # Rückgabe
        if tic['proof']['por'] == 'valid' and tic['proof']['mci'] >= 0.9:
            status_str = "ok"
        else:
            status_str = "hold"

        lyapunov_series = convergence_info.get('lyapunov_series', [])
        gate_fsm.update(status_str, snapshot, tic, lyapunov_series)

        try:
            _upsert_quality_vector(
                snapshot,
                tic,
                snapshot_id=snapshot_id,
                status=status_str,
                convergence=convergence_info,
            )
        except Exception as exc:
            try:
                logger.log_error(
                    "API",
                    exc,
                    {
                        "endpoint": "/solve",
                        "snapshot_id": snapshot_id,
                        "tic_id": tic.get("tic_id"),
                        "stage": "quality_index",
                    },
                )
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"failed to index solve output: {exc}") from exc

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        active_payload = {
            "snapshot_id": snapshot_id,
            "tic_id": tic['tic_id'],
            "status": status_str,
        }
        mode_state.setdefault("active_contingent", {})
        mode_state["active_contingent"] = active_payload

        scorpio_sync.advance(active=active_payload, gate=gate_fsm.snapshot())
        scorpio_snapshot = scorpio_sync.snapshot()

        mode_state.update({
            "mode": "commit" if status_str == "ok" else "hold",
            "tick_ms": round(duration_ms, 3),
            "tick_no": scorpio_snapshot["tick_no"],
            "tick_proof": scorpio_snapshot["tick_proof"],
            "ouroboros": scorpio_snapshot["ouroboros"],
            "seed": scorpio_snapshot["seed"],
        })

        metrics.observe("solve", duration_ms)
        trace_emitter.span(
            "solve",
            {
                "snapshot_id": snapshot_id,
                "tic_id": tic['tic_id'],
                "status": status_str,
                "delta_pi": delta_pi,
                "duration_ms": round(duration_ms, 6),
            },
        )

        response_payload = {
            "status": status_str,
            "tic_id": tic['tic_id'],
            "steps": convergence_info['iterations'],
            "converged": convergence_info['converged'],
            "lyapunov_series": lyapunov_series,
            "invariants": tic['invariants'],
            "tick": scorpio_snapshot,
        }

        if por_override_active:
            metadata = dict(tic.get('meta') or {})
            metadata['por_override'] = 'fire'
            response_payload['metadata'] = metadata

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        mode_state.update({
            "mode": "error",
            "tick_ms": 0.0,
            "tick_no": 0,
            "active_contingent": {"snapshot_id": snapshot_id},
        })
        logger.log_error("API", e, {"endpoint": "/solve", "snapshot_id": snapshot_id})
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gate/fsm")
async def get_gate_fsm(token: str = Depends(require_bearer)):
    """Expose the current gate finite state machine snapshot."""
    return gate_fsm.snapshot()


@app.get("/mode")
async def get_mode(token: str = Depends(require_bearer)):
    """Expose current scheduler mode and tick metadata."""
    scorpio_snapshot = scorpio_sync.snapshot()
    payload = {
        "mode": mode_state.get("mode"),
        "tick_ms": mode_state.get("tick_ms"),
        "tick_no": scorpio_snapshot.get("tick_no"),
        "tick_proof": scorpio_snapshot.get("tick_proof"),
        "active_contingent": mode_state.get("active_contingent"),
        "ouroboros": scorpio_snapshot.get("ouroboros"),
        "seed": scorpio_snapshot.get("seed"),
    }
    trace_emitter.span("mode", payload)
    return payload


@app.post("/ledger")
async def append_ledger(tic_id: str, snapshot_id: str):
    """
    SPEC-002: Ledger-Endpunkt.
    Erzeugt MEF-Block, persistiert in C:/MEF/ledger/{index}.mef.
    """
    try:
        # Lade TIC und Snapshot
        tic = storage.retrieve_tic(tic_id)
        if not tic:
            raise HTTPException(status_code=404, detail="TIC not found")
        
        snapshot = storage.retrieve_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        # Prüfe Commit-Bedingungen
        if not tic_crystallizer.should_commit(tic):
            logger.log_event(
                "LEDGER_HOLD",
                "API",
                {"tic_id": tic_id, "reason": "commit_conditions_not_met"},
                severity="WARNING"
            )
            return {"status": "hold", "reason": "commit conditions not met"}
        
        # Append Block
        success, block = ledger.append_block(tic, snapshot)
        
        if not success:
            raise HTTPException(status_code=500, detail=f"Ledger append failed: {block}")
        
        # Speichere Block als Einzeldatei (SPEC-002)
        block_file = LEDGER_PATH / f"{block['index']}.mef"
        with open(block_file, 'wb') as f:
            f.write(orjson.dumps(block, option=orjson.OPT_SORT_KEYS | orjson.OPT_INDENT_2))
        
        # Update index.json mit last_hash (SPEC-002 Punkt 8)
        index_file = LEDGER_PATH / "index.json"
        index_data = {
            "last_index": block['index'],
            "last_hash": block['hash'],
            "updated": datetime.utcnow().isoformat() + 'Z'
        }
        with open(index_file, 'wb') as f:
            f.write(orjson.dumps(index_data, option=orjson.OPT_SORT_KEYS))
        
        # Audit Event (SPEC-002 Punkt 8)
        logger.log_event(
            "LEDGER_COMMIT",
            "API",
            {
                "type": "commit",
                "block": block['index'],
                "hash": block['hash'],
                "tic_id": tic_id
            }
        )
        
        return {
            "index": block['index'],
            "hash": block['hash'],
            "previous_hash": block['previous_hash'],
            "stored": str(block_file)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.log_error("API", e, {"endpoint": "/ledger", "tic_id": tic_id})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/spiral/{id}")
async def get_spiral(id: str):
    """Hole Spiral Snapshot."""
    snapshot = storage.retrieve_snapshot(id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snapshot

@app.get("/tic/{id}")
async def get_tic(id: str):
    """Hole TIC."""
    tic = storage.retrieve_tic(id)
    if not tic:
        raise HTTPException(status_code=404, detail="TIC not found")
    return tic

@app.get("/ledger/{index}")
async def get_ledger_block(index: int):
    """Hole Ledger Block."""
    block = ledger.get_block(index)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block {index} not found")
    return block

@app.get("/audit")
async def get_audit():
    """
    SPEC-002: Audit-Endpunkt.
    Packt ledger/*.mef, index.json, logs/*.jsonl als ZIP.
    """
    import zipfile
    from io import BytesIO
    
    # Erstelle ZIP im Memory
    zip_buffer = BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Ledger Blocks
        for mef_file in LEDGER_PATH.glob("*.mef"):
            zf.write(mef_file, f"ledger/{mef_file.name}")
        
        # Index
        index_file = LEDGER_PATH / "index.json"
        if index_file.exists():
            zf.write(index_file, "ledger/index.json")
        
        # Logs
        for log_file in LOGS_PATH.glob("*.jsonl"):
            zf.write(log_file, f"logs/{log_file.name}")
        for log_file in LOGS_PATH.glob("*.log"):
            zf.write(log_file, f"logs/{log_file.name}")
    
    zip_buffer.seek(0)
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=audit_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
        }
    )


@app.get("/stats")
async def get_stats(token: str = Depends(require_bearer)):
    return {
        "metrics": metrics.snapshot(),
        "traces": trace_emitter.snapshot(),
        "delta_pi_violations": delta_pi_violations,
    }

# Main für direkte Ausführung
def main():
    host = os.getenv("BIND_HOST") or os.getenv("SERVER_HOST") or "0.0.0.0"
    port_env = (
        os.getenv("PORT")
        or os.getenv("BIND_PORT")
        or os.getenv("SERVER_PORT")
        or "8080"
    )
    try:
        port = int(port_env)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        port = 8080

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
