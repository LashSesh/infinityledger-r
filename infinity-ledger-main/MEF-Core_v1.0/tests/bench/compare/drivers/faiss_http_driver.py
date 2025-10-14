from __future__ import annotations

import os
from typing import List, Sequence

import httpx
import orjson

from .base import Driver, SearchResults, UpsertItem, Vector


class FaissHTTPDriver(Driver):
    """HTTP client that talks to the FAISS FastAPI microservice."""

    name = "faiss-http"

    def __init__(self) -> None:
        base_url = os.getenv("FAISS_URL", "http://faiss-api:8090")
        self._base_url = base_url.rstrip("/")
        self._timeout = float(os.getenv("HTTPX_TIMEOUT", "30.0"))
        self._client: httpx.Client | None = None

    def connect(self) -> None:
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Connection": "keep-alive", "Content-Type": "application/json"},
        )
        response = self._client.post("/clear")
        response.raise_for_status()

    def clear(self) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before clear()")
        response = self._client.post("/clear")
        response.raise_for_status()

    def upsert(self, items: List[UpsertItem]) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        if not items:
            return
        payload = {
            "vectors": [
                {
                    "id": str(item["id"]),
                    "values": [float(value) for value in item["values"]],
                }
                for item in items
            ]
        }
        response = self._client.post("/upsert", content=orjson.dumps(payload))
        response.raise_for_status()

    def search(self, queries: Sequence[Vector], k: int) -> SearchResults:
        if self._client is None:
            raise RuntimeError("connect() must be called before search()")
        payload = {
            "queries": [[float(value) for value in query] for query in queries],
            "k": int(k),
        }
        response = self._client.post("/search", content=orjson.dumps(payload))
        response.raise_for_status()
        data = response.json()
        hits_payload = data.get("hits", [])
        results: SearchResults = []
        for entries in hits_payload:
            target_hits = []
            for entry in entries:
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


__all__ = ["FaissHTTPDriver"]
