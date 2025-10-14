from __future__ import annotations

import os
from typing import List, Sequence

import httpx
import orjson

from .base import Driver, SearchResults, UpsertItem, Vector


class MEFHTTPDriver(Driver):
    """Driver that exercises the MEF HTTP API."""

    name = "mef-http"

    def __init__(self) -> None:
        base = os.getenv("MEF_BASE_URL") or os.getenv("QUALITY_BASE_URL") or "http://localhost:8080"
        self._base_url = base.rstrip("/")
        self._timeout = float(os.getenv("HTTPX_TIMEOUT", "30.0"))
        self._metric = os.getenv("ANN_METRIC", "cosine")
        self._collection = (
            os.getenv("COMPARE_COLLECTION")
            or os.getenv("QUALITY_COLLECTION")
            or "spiral"
        )
        self._client: httpx.Client | None = None

    def connect(self) -> None:
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Connection": "keep-alive", "Content-Type": "application/json"},
        )
        response = self._client.get("/healthz")
        response.raise_for_status()

    def clear(self) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before clear()")
        payload = {"vectors": [], "epoch": 1, "metric": self._metric}
        response = self._client.post(
            f"/collections/{self._collection}/upsert",
            content=orjson.dumps(payload),
        )
        if response.status_code not in {200, 204, 404}:
            response.raise_for_status()

    def upsert(self, items: List[UpsertItem]) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        if not items:
            return
        vectors = []
        for item in items:
            entry = {
                "id": str(item["id"]),
                "vector": [float(value) for value in item["values"]],
            }
            metadata = item.get("metadata")
            if metadata:
                entry["metadata"] = dict(metadata)
            vectors.append(entry)
        payload = {
            "vectors": vectors,
            "epoch": int(items[0].get("epoch", 1)),
            "metric": self._metric,
        }
        response = self._client.post(
            f"/collections/{self._collection}/upsert",
            content=orjson.dumps(payload),
        )
        response.raise_for_status()

    def search(self, queries: Sequence[Vector], k: int) -> SearchResults:
        if self._client is None:
            raise RuntimeError("connect() must be called before search()")
        results: SearchResults = []
        for query in queries:
            payload = {
                "collection": self._collection,
                "query_vector": [float(value) for value in query],
                "top_k": int(k),
                "mode": "ann",
                "solve": False,
                "membership_proof": False,
                "pipeline_proof": False,
            }
            response = self._client.post("/search", content=orjson.dumps(payload))
            response.raise_for_status()
            data = response.json()
            hits_payload = data.get("results", [])
            target_hits = []
            for entry in hits_payload:
                identifier = entry.get("id")
                score = entry.get("score")
                if identifier is None or score is None:
                    continue
                target_hits.append((str(identifier), float(score)))
            results.append(target_hits)
        return results

    def __del__(self) -> None:  # pragma: no cover - GC guard
        if self._client is not None:
            self._client.close()


__all__ = ["MEFHTTPDriver"]
