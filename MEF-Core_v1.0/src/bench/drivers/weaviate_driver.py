"""Driver for Weaviate using the official Python client."""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class WeaviateDriver(VectorStoreDriver):
    """Benchmark driver that integrates with a Weaviate cluster."""

    name = "Weaviate"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._base_url = (os.getenv("WEAVIATE_URL") or "").rstrip("/")
        self._client = None
        self._dimension: Optional[int] = None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        if not self._base_url:
            raise DriverUnavailable(self.name, "WEAVIATE_URL not configured")
        try:
            import weaviate  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise DriverUnavailable(self.name, "weaviate-client package is not installed") from exc

        try:
            self._client = weaviate.Client(self._base_url)
            self._client.schema.get()
        except Exception as exc:  # pragma: no cover - network guard
            raise DriverUnavailable(self.name, f"unable to reach Weaviate: {exc}") from exc

    def clear(self, namespace: str) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before clear()")
        class_name = self._class_name(namespace)
        try:
            self._client.schema.delete_class(class_name)
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
        class_name = self._class_name(namespace)
        entries = list(items)
        if not entries:
            return
        if self._dimension is None:
            self._dimension = len(entries[0][1])
        self._ensure_class(namespace, self._dimension)
        self._client.batch.configure(batch_size=batch_size)
        with self._client.batch as batch:
            for identifier, vector, _metadata in entries:
                prepared = self._prepare_vector(vector)
                batch.add_data_object(
                    data_object={},
                    class_name=class_name,
                    uuid=identifier,
                    vector=prepared,
                )

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        if self._client is None:
            raise RuntimeError("connect() must be called before search()")
        class_name = self._class_name(namespace)
        prepared = self._prepare_vector(query)
        result = (
            self._client.query.get(class_name, [])
            .with_limit(int(k))
            .with_additional(["id", "distance"])
            .with_near_vector({"vector": prepared})
            .do()
        )
        data = result.get("data", {}) if isinstance(result, dict) else {}
        get_payload = data.get("Get", {}) if isinstance(data, dict) else {}
        class_results = get_payload.get(class_name) or []
        hits: List[Tuple[str, float]] = []
        for entry in class_results:
            additional = entry.get("_additional", {}) if isinstance(entry, dict) else {}
            identifier = additional.get("id")
            distance = additional.get("distance", 0.0)
            if identifier is None:
                continue
            hits.append((str(identifier), float(distance)))
        return hits[:k]

    # ------------------------------------------------------------------
    def _ensure_class(self, namespace: str, dimension: int) -> None:
        if self._client is None:
            raise RuntimeError("connect() must be called before upsert()")
        class_name = self._class_name(namespace)
        existing = self._client.schema.get()
        for entry in existing.get("classes", []):
            if entry.get("class") == class_name:
                return
        distance = {
            "cosine": "cosine",
            "ip": "dot",
            "l2": "l2-squared",
        }.get(self.metric, "cosine")
        config = {
            "class": class_name,
            "description": "Benchmark dataset",
            "vectorizer": "none",
            "moduleConfig": {},
            "vectorIndexType": "hnsw",
            "vectorIndexConfig": {"distance": distance},
        }
        self._client.schema.create_class(config)
        self._dimension = dimension

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

    def _class_name(self, namespace: str) -> str:
        token = re.sub(r"[^0-9A-Za-z]", "", namespace)
        if not token:
            token = "Namespace"
        if not token[0].isalpha():
            token = f"N{token}"
        return token[0].upper() + token[1:]


__all__ = ["WeaviateDriver"]
