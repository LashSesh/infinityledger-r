"""Driver for Pinecone's managed vector database."""

from __future__ import annotations

import os
import time
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class PineconeDriver(VectorStoreDriver):
    """Benchmark driver that integrates with Pinecone if credentials are provided."""

    name = "Pinecone"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._api_key = os.getenv("PINECONE_API_KEY")
        self._environment = os.getenv("PINECONE_ENV")
        self._client = None
        self._dimension: Optional[int] = None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        if not self._api_key:
            raise DriverUnavailable(self.name, "PINECONE_API_KEY not configured")
        try:
            from pinecone import Pinecone, PodSpec  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise DriverUnavailable(self.name, "pinecone-client package is not installed") from exc

        kwargs = {"api_key": self._api_key}
        if self._environment:
            kwargs["environment"] = self._environment
        try:
            self._client = Pinecone(**kwargs)
        except Exception as exc:  # pragma: no cover - network guard
            raise DriverUnavailable(self.name, f"unable to reach Pinecone: {exc}") from exc

    def clear(self, namespace: str) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before clear()")
        try:
            if namespace in self._client.list_indexes().names:
                self._client.delete_index(namespace)
                self._wait_for_index_deletion(namespace)
        except Exception:
            pass
        self._dimension = None

    # ------------------------------------------------------------------
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        entries = list(items)
        if not entries:
            return
        if self._dimension is None:
            self._dimension = len(entries[0][1])
            self._ensure_index(namespace, self._dimension)
        index = self._client.Index(namespace)
        batch: List[dict] = []
        for identifier, vector, metadata in entries:
            prepared = self._prepare_vector(vector)
            record = {"id": identifier, "values": prepared}
            if metadata:
                record["metadata"] = dict(metadata)
            batch.append(record)
            if len(batch) >= batch_size:
                index.upsert(vectors=batch)
                batch = []
        if batch:
            index.upsert(vectors=batch)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        if self._client is None:
            raise RuntimeError("connect() must be called before search()")
        index = self._client.Index(namespace)
        prepared = self._prepare_vector(query)
        response = index.query(vector=prepared, top_k=int(k), include_values=False)
        matches = getattr(response, "matches", [])
        hits: List[Tuple[str, float]] = []
        for match in matches:
            identifier = getattr(match, "id", None)
            score = getattr(match, "score", 0.0)
            if identifier is None:
                continue
            hits.append((str(identifier), float(score)))
        return hits[:k]

    # ------------------------------------------------------------------
    def _ensure_index(self, namespace: str, dimension: int) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        metric = {
            "cosine": "cosine",
            "ip": "dotproduct",
            "l2": "euclidean",
        }.get(self.metric, "cosine")
        existing = self._client.list_indexes()
        names = getattr(existing, "names", existing)
        if namespace in names:
            self._wait_for_index_ready(namespace)
            return
        try:
            from pinecone import PodSpec  # type: ignore
        except Exception:
            PodSpec = None  # type: ignore
        kwargs = {
            "name": namespace,
            "dimension": int(dimension),
            "metric": metric,
        }
        if PodSpec is not None and self._environment:
            kwargs["spec"] = PodSpec(environment=self._environment)
        self._client.create_index(**kwargs)
        self._wait_for_index_ready(namespace)

    def _wait_for_index_ready(self, namespace: str, timeout: float = 300.0) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        deadline = time.time() + timeout
        while True:
            try:
                description = self._client.describe_index(namespace)
            except Exception as exc:  # pragma: no cover - network guard
                if time.time() >= deadline:
                    raise RuntimeError(
                        f"timed out while waiting for Pinecone index '{namespace}' to become ready"
                    ) from exc
                time.sleep(1.0)
                continue

            status = getattr(description, "status", None)
            if isinstance(status, dict):
                ready = status.get("ready")
                state = status.get("state")
            else:
                ready = getattr(status, "ready", None)
                state = getattr(status, "state", None)

            if ready or (state and state.lower() == "ready"):
                return

            if time.time() >= deadline:
                raise RuntimeError(
                    f"timed out while waiting for Pinecone index '{namespace}' to become ready"
                )

            time.sleep(1.0)

    def _wait_for_index_deletion(self, namespace: str, timeout: float = 120.0) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before clear()")
        deadline = time.time() + timeout
        while True:
            try:
                existing = self._client.list_indexes()
            except Exception as exc:  # pragma: no cover - network guard
                if time.time() >= deadline:
                    raise RuntimeError(
                        f"timed out while waiting for Pinecone index '{namespace}' to be deleted"
                    ) from exc
                time.sleep(1.0)
                continue

            names = getattr(existing, "names", existing)
            if namespace not in names:
                return

            if time.time() >= deadline:
                raise RuntimeError(
                    f"timed out while waiting for Pinecone index '{namespace}' to be deleted"
                )

            time.sleep(1.0)

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


__all__ = ["PineconeDriver"]
