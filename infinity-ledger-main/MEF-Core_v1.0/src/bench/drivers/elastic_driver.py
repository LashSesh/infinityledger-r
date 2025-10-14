"""Driver for Elasticsearch/OpenSearch dense vector kNN APIs."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import requests

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class ElasticDriver(VectorStoreDriver):
    """Benchmark driver targeting an Elasticsearch-compatible endpoint."""

    name = "Elastic"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._base_url = (os.getenv("ELASTIC_URL") or "").rstrip("/")
        self._session: Optional[requests.Session] = None
        self._dimension: Optional[int] = None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        if not self._base_url:
            raise DriverUnavailable(self.name, "ELASTIC_URL not configured")
        session = requests.Session()
        try:
            response = session.get(f"{self._base_url}/_cluster/health", timeout=5)
        except requests.RequestException as exc:  # pragma: no cover - network guard
            raise DriverUnavailable(self.name, f"unable to reach Elasticsearch: {exc}") from exc
        if response.status_code >= 500:
            raise DriverUnavailable(self.name, f"cluster unhealthy: HTTP {response.status_code}")
        self._session = session

    def clear(self, namespace: str) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before clear()")
        response = self._session.delete(f"{self._base_url}/{namespace}", timeout=15)
        if response.status_code not in {200, 202, 204, 404}:
            response.raise_for_status()
        self._dimension = None

    # ------------------------------------------------------------------
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before upsert()")
        entries = list(items)
        if not entries:
            return
        if self._dimension is None:
            self._dimension = len(entries[0][1])
            self._ensure_index(namespace, self._dimension)
        bulk_lines: List[str] = []
        for identifier, vector, _metadata in entries:
            prepared = self._prepare_vector(vector)
            action = {"index": {"_index": namespace, "_id": identifier}}
            bulk_lines.append(self._json(action))
            bulk_lines.append(self._json({"vector": prepared}))
            if len(bulk_lines) // 2 >= batch_size:
                self._flush(namespace, bulk_lines)
                bulk_lines = []
        if bulk_lines:
            self._flush(namespace, bulk_lines)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        if self._session is None:
            raise RuntimeError("connect() must be called before search()")
        prepared = self._prepare_vector(query)
        num_candidates = max(int(k) * 4, int(k))
        response = self._session.get(
            f"{self._base_url}/{namespace}/_search",
            json={
                "size": int(k),
                "knn": {
                    "field": "vector",
                    "query_vector": prepared,
                    "k": int(k),
                    "num_candidates": max(num_candidates, int(k)),
                },
                "_source": False,
            },
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        hits_payload = payload.get("hits", {}).get("hits", [])
        hits: List[Tuple[str, float]] = []
        for entry in hits_payload:
            identifier = entry.get("_id")
            score = entry.get("_score", 0.0)
            if identifier is None:
                continue
            hits.append((str(identifier), float(score)))
        return hits[:k]

    # ------------------------------------------------------------------
    def _ensure_index(self, namespace: str, dimension: int) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before upsert()")
        similarity = {
            "cosine": "cosine",
            "ip": "dot_product",
            "l2": "l2_norm",
        }.get(self.metric, "cosine")
        payload = {
            "settings": {
                "index": {
                    "knn": True,
                }
            },
            "mappings": {
                "properties": {
                    "vector": {
                        "type": "dense_vector",
                        "dims": int(dimension),
                        "index": True,
                        "similarity": similarity,
                    }
                }
            },
        }
        response = self._session.put(f"{self._base_url}/{namespace}", json=payload, timeout=15)
        if response.status_code in {200, 201}:
            return
        if response.status_code == 400 and "resource_already_exists_exception" in response.text:
            return
        if response.status_code == 404:
            # older clusters may require _doc suffix – ignore for optional targets
            raise DriverUnavailable(self.name, "Elasticsearch server rejected index creation")
        response.raise_for_status()

    def _flush(self, namespace: str, lines: List[str]) -> None:
        if self._session is None:
            raise RuntimeError("connect() must be called before upsert()")
        body = "\n".join(lines) + "\n"
        response = self._session.post(f"{self._base_url}/_bulk", data=body, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError("bulk ingest reported errors")

    def _prepare_vector(self, vector: Sequence[float]) -> List[float]:
        array = np.asarray(vector, dtype="float32")
        if self._dimension is not None and array.shape[0] != self._dimension:
            raise ValueError(
                f"dimension mismatch: expected {self._dimension}, received {array.shape[0]}"
            )
        if self._dimension is None:
            self._dimension = array.shape[0]
        if self.metric in {"cosine", "ip"}:
            norm = float(np.linalg.norm(array))
            if norm:
                array = array / norm
        return array.astype("float32").tolist()

    @staticmethod
    def _json(payload: dict) -> str:
        import json

        return json.dumps(payload, separators=(",", ":"))


__all__ = ["ElasticDriver"]
