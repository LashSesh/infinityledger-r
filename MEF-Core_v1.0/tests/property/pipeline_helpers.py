import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from ..quality_utils import (
    QUALITY_COLLECTION,
    hash_vector,
    request_json,
    request_raw,
    sort_hits,
)


class SolveHoldDueToPOR(RuntimeError):
    """Raised when `/solve` refuses a snapshot because PoR is invalid."""

    def __init__(self, snapshot_id: str, por_status: str, payload: Mapping[str, Any]):
        super().__init__(f"Snapshot {snapshot_id} rejected: PoR status {por_status!r}")
        self.snapshot_id = snapshot_id
        self.por_status = por_status
        self.payload = payload


def _ci_bypass_por(headers: Optional[Mapping[str, Any]] = None) -> bool:
    """Return ``True`` when CI headers or env should suppress PoR holds."""

    if os.getenv("CI_NO_POR_HOLDS") == "1":
        return True
    if not headers:
        return False
    lowered = {str(k).lower(): str(v).lower() for k, v in headers.items()}
    if lowered.get("x-ci-mode") == "true" or lowered.get("x-golden") == "true":
        return True
    return lowered.get("x-por-override") in {"true", "test-golden"}


@dataclass
class RoundtripResult:
    snapshot_id: str
    tic_id: str
    vector: List[float]
    vector_hash: str
    commit_root: Optional[str]
    lyapunov_series: List[float]
    delta_pi: float
    stability: Optional[float]
    hits: List[Dict[str, Any]]
    pipeline_proofs: List[Optional[str]]
    membership_proofs: List[Optional[Mapping[str, Any]]]
    solve_status: str
    solve_payload: Mapping[str, Any]
    search_payload: Mapping[str, Any]
    search_request: Mapping[str, Any]
    search_headers: Mapping[str, Any]
    collection: str
    top_k: int
    provider: Optional[str]
    provider_used: Optional[str]
    proof_context: Optional[Mapping[str, Any]]
    search_plan: Optional[Mapping[str, Any]]


def _base_payload(sample: Mapping[str, Any]) -> Dict[str, Any]:
    timestamp = sample.get("timestamp") or "2025-01-01T00:00:00Z"
    return {
        "id": sample.get("id"),
        "text": sample.get("text"),
        "timestamp": timestamp,
        "meta": {
            "quality": True,
            "source": "quality-suite",
            "dataset_id": sample.get("id"),
        },
    }


def run_roundtrip(
    sample: Mapping[str, Any],
    *,
    top_k: int = 5,
    membership_proof: bool = True,
    pipeline_proof: bool = True,
    collection: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
    por_override: bool = False,
) -> RoundtripResult:
    effective_headers: Dict[str, str] = dict(headers or {})
    if por_override:
        effective_headers.setdefault("X-POR-Override", "test-golden")
        effective_headers.setdefault("X-Golden-Run", "true")
        effective_headers.setdefault("X-CI-Mode", "true")

    body = _base_payload(sample)
    acquisition = request_json(
        "POST", "/acquisition", json_body=body, headers=effective_headers
    )
    snapshot_id = acquisition["snapshot_id"]

    por_status = str(acquisition.get("por", ""))
    if por_status.lower() != "valid" and not _ci_bypass_por(effective_headers):
        raise SolveHoldDueToPOR(snapshot_id, por_status, acquisition)

    solve = request_json(
        "POST", f"/solve?snapshot_id={snapshot_id}", headers=effective_headers
    )
    tic_id = solve["tic_id"]

    tic = request_json("GET", f"/tic/{tic_id}", headers=effective_headers)
    vector = list(tic.get("fixpoint") or tic.get("vector") or [])

    collection_name = collection or QUALITY_COLLECTION
    search_request = {
        "collection": collection_name,
        "query_vector": vector,
        "top_k": top_k,
        "mode": "ann",
        "membership_proof": membership_proof,
        "pipeline_proof": pipeline_proof,
    }
    search_response_raw = request_raw(
        "POST",
        "/search",
        json_body=search_request,
        headers=effective_headers,
    )
    search_response_raw.raise_for_status()
    search_response = search_response_raw.json()
    search_headers = dict(search_response_raw.headers)

    try:
        plan_snapshot = request_json(
            "GET", "/debug/search-plan", headers=effective_headers
        )
    except Exception:
        plan_snapshot = {}

    provider_used = None
    provider_name = None
    if isinstance(plan_snapshot, Mapping):
        provider_meta = plan_snapshot.get("provider_used")
        if isinstance(provider_meta, Mapping):
            provider_name = provider_meta.get("name")
            provider_used = provider_meta.get("name")
            provider_version = provider_meta.get("version")
            if provider_used and provider_version:
                provider_used = f"{provider_used}@{provider_version}"
        if not provider_name:
            provider_name = plan_snapshot.get("index")
    if provider_name is None:
        try:
            status_snapshot = request_json(
                "GET",
                f"/index/status?collection={collection_name}",
            )
        except Exception:
            status_snapshot = {}
        if isinstance(status_snapshot, Mapping):
            params = status_snapshot.get("params") if isinstance(status_snapshot.get("params"), Mapping) else {}
            provider_name = params.get("provider") or status_snapshot.get("provider")
    if provider_used is None:
        provider_used = search_response.get("provider_used")
        if isinstance(provider_used, Mapping):
            provider_used = provider_used.get("name")
    if provider_used is None:
        provider_used = search_headers.get("X-Provider-Used")

    hits = sort_hits(search_response.get("results", []))
    commit_root = None
    commit_payload = search_response.get("commit")
    if isinstance(commit_payload, Mapping):
        commit_root = commit_payload.get("commit_root")

    invariants = solve.get("invariants", {})

    proof_context = search_response.get("proof_context")
    if isinstance(proof_context, Mapping):
        provider_name = proof_context.get("provider") or provider_name

    return RoundtripResult(
        snapshot_id=snapshot_id,
        tic_id=tic_id,
        vector=vector,
        vector_hash=hash_vector(vector),
        commit_root=commit_root,
        lyapunov_series=list(solve.get("lyapunov_series") or []),
        delta_pi=float(invariants.get("delta_pi", 0.0)),
        stability=float(invariants.get("stability", invariants.get("retention", 0.0)))
        if invariants
        else None,
        hits=hits,
        pipeline_proofs=[hit.get("pipeline_proof") for hit in hits],
        membership_proofs=[hit.get("membership_proof") for hit in hits],
        solve_status=str(solve.get("status", "hold")),
        solve_payload=solve,
        search_payload=search_response,
        search_request=search_request,
        search_headers=search_headers,
        collection=collection_name,
        top_k=top_k,
        provider=provider_name,
        provider_used=provider_used,
        proof_context=proof_context if isinstance(proof_context, Mapping) else None,
        search_plan=plan_snapshot if isinstance(plan_snapshot, Mapping) else None,
    )


def sample_dataset(
    dataset: List[Mapping[str, Any]],
    *,
    count: int,
    seed: int = 123,
) -> List[Mapping[str, Any]]:
    rng = random.Random(seed)
    if count >= len(dataset):
        return list(dataset)
    return rng.sample(dataset, count)


def wait_for_commit_consistency(delay: float = 0.5) -> None:
    time.sleep(max(0.0, delay))


def timestamp() -> str:
    return datetime.utcnow().isoformat() + "Z"
