"""Driver that exercises the MEF HTTP API for apples-to-apples comparisons."""

from __future__ import annotations

import os
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

from tests import quality_utils

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class MEFDriver(VectorStoreDriver):
    """Driver that talks to the MEF REST API used by the existing bench."""

    name = "MEF"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        base = os.getenv("MEF_BASE_URL") or os.getenv("QUALITY_BASE_URL")
        self._base_url = (base or "http://localhost:8080").rstrip("/")
        self._session: Optional[requests.Session] = None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        session = quality_utils.build_session()
        health_url = f"{self._base_url}/healthz"
        try:
            response = session.get(health_url, timeout=5)
        except requests.RequestException as exc:  # pragma: no cover - network guard
            raise DriverUnavailable(self.name, f"failed to contact {health_url}: {exc}") from exc
        if response.status_code >= 500:
            raise DriverUnavailable(self.name, f"service unhealthy: HTTP {response.status_code}")
        self._session = session

    def clear(self, namespace: str) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before clear()")
        payload = {"vectors": [], "epoch": 1, "metric": self.metric}
        url = f"{self._base_url}/collections/{namespace}/upsert"
        response = self._session.post(url, json=payload, timeout=15)
        if response.status_code in {200, 204, 404}:
            return
        if response.status_code >= 500:
            raise RuntimeError(f"failed to clear namespace {namespace}: HTTP {response.status_code}")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:  # pragma: no cover - diagnostics
            raise RuntimeError(f"clear namespace failed: {exc}") from exc

    # ------------------------------------------------------------------
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before upsert()")
        batch: List[dict] = []
        for identifier, vector, metadata in items:
            payload = {
                "id": identifier,
                "vector": [float(value) for value in vector],
            }
            if metadata:
                payload["metadata"] = dict(metadata)
            batch.append(payload)
            if len(batch) >= batch_size:
                self._flush_batch(namespace, batch)
                batch = []
        if batch:
            self._flush_batch(namespace, batch)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        if self._session is None:
            raise RuntimeError("connect() must be called before search()")
        url = f"{self._base_url}/search"
        response = self._session.post(
            url,
            json={
                "collection": namespace,
                "query_vector": [float(value) for value in query],
                "top_k": int(k),
                "mode": "ann",
                "solve": False,
                "membership_proof": False,
                "pipeline_proof": False,
            },
            timeout=quality_utils.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        hits: List[Tuple[str, float]] = []
        for entry in results:
            identifier = entry.get("id")
            score = entry.get("score", 0.0)
            if identifier is None:
                continue
            hits.append((str(identifier), float(score)))
        return hits[:k]

    # ------------------------------------------------------------------
    def _flush_batch(self, namespace: str, batch: List[Mapping[str, object]]) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before upsert()")
        url = f"{self._base_url}/collections/{namespace}/upsert"
        response = self._session.post(
            url,
            json={
                "vectors": list(batch),
                "epoch": 1,
                "metric": self.metric,
            },
            timeout=quality_utils.REQUEST_TIMEOUT,
        )
        response.raise_for_status()


__all__ = ["MEFDriver"]
