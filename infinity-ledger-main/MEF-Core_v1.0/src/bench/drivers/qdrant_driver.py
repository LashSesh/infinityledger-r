"""Driver for Qdrant's HTTP API."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence, Tuple

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from qdrant_client.http.exceptions import UnexpectedResponse

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class QdrantDriver(VectorStoreDriver):
    """Benchmark driver that interacts with a Qdrant deployment via qdrant-client."""

    name = "Qdrant"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._base_url = (os.getenv("QDRANT_URL") or "").rstrip("/")
        self._client: Optional[QdrantClient] = None
        self._dimension: Optional[int] = None

    def connect(self) -> None:
        if not self._base_url:
            raise DriverUnavailable(self.name, "QDRANT_URL not configured")
        try:
            client = QdrantClient(url=self._base_url, prefer_grpc=False, timeout=5.0)
            client.get_health()
        except Exception as exc:  # pragma: no cover - network flakes
            raise DriverUnavailable(self.name, f"unable to connect to Qdrant: {exc}") from exc
        self._client = client

    def clear(self, namespace: str) -> None:
        client = self._require_client()
        try:
            client.delete_collection(namespace)
        except UnexpectedResponse as exc:
            if exc.status_code != 404:
                raise
        except Exception as exc:  # pragma: no cover - defensive
            raise DriverUnavailable(self.name, f"failed to clear collection: {exc}") from exc
        self._dimension = None

    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        client = self._require_client()
        batch: List[rest_models.PointStruct] = []
        for identifier, vector, metadata in items:
            if self._dimension is None:
                self._dimension = len(vector)
                self._ensure_collection(client, namespace, self._dimension)
            payload = rest_models.PointStruct(
                id=identifier,
                vector=[float(value) for value in vector],
                payload=dict(metadata) if metadata else None,
            )
            batch.append(payload)
            if len(batch) >= batch_size:
                self._flush(client, namespace, batch)
                batch = []
        if batch:
            self._flush(client, namespace, batch)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        client = self._require_client()
        try:
            results = client.search(
                collection_name=namespace,
                query_vector=[float(value) for value in query],
                limit=int(k),
                with_payload=False,
                with_vectors=False,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise DriverUnavailable(self.name, f"search failed: {exc}") from exc
        hits: List[Tuple[str, float]] = []
        for entry in results:
            identifier = entry.id
            score = entry.score if entry.score is not None else 0.0
            hits.append((str(identifier), float(score)))
        return hits[:k]

    def _require_client(self) -> QdrantClient:
        if self._client is None:
            raise RuntimeError("connect() must be called before using the driver")
        return self._client

    def _ensure_collection(self, client: QdrantClient, namespace: str, dimension: int) -> None:
        distance = {
            "cosine": rest_models.Distance.COSINE,
            "ip": rest_models.Distance.DOT,
            "l2": rest_models.Distance.EUCLID,
        }.get(self.metric, rest_models.Distance.COSINE)
        vectors_config = rest_models.VectorParams(size=int(dimension), distance=distance)
        try:
            client.recreate_collection(
                collection_name=namespace,
                vectors_config=vectors_config,
                wait=True,
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise DriverUnavailable(self.name, f"failed to ensure collection: {exc}") from exc

    def _flush(
        self,
        client: QdrantClient,
        namespace: str,
        batch: List[rest_models.PointStruct],
    ) -> None:
        try:
            client.upsert(collection_name=namespace, points=batch, wait=True)
        except Exception as exc:  # pragma: no cover - defensive
            raise DriverUnavailable(self.name, f"failed to upsert batch: {exc}") from exc


__all__ = ["QdrantDriver"]
