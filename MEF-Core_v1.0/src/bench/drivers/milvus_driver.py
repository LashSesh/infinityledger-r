"""Driver for Milvus using the official pymilvus client."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .base import DriverUnavailable, UpsertItem, Vector, VectorStoreDriver


class MilvusDriver(VectorStoreDriver):
    """Benchmark driver that uses the pymilvus client to query Milvus."""

    name = "Milvus"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._host = os.getenv("MILVUS_HOST")
        self._port = os.getenv("MILVUS_PORT", "19530")
        self._utility = None
        self._Collection = None  # type: ignore[assignment]
        self._FieldSchema = None  # type: ignore[assignment]
        self._CollectionSchema = None  # type: ignore[assignment]
        self._DataType = None  # type: ignore[assignment]
        self._dimension: Optional[int] = None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        if not self._host:
            raise DriverUnavailable(self.name, "MILVUS_HOST not configured")
        try:
            from pymilvus import (  # type: ignore
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
                connections,
                utility,
            )
        except Exception as exc:  # pragma: no cover - optional dependency guard
            raise DriverUnavailable(self.name, "pymilvus package is not installed") from exc

        try:
            connections.connect(alias="benchmark", host=self._host, port=self._port)
        except Exception as exc:  # pragma: no cover - connection guard
            raise DriverUnavailable(
                self.name,
                f"failed to connect to Milvus at {self._host}:{self._port}. "
                "Ensure Milvus service is running and healthy. "
                f"Error: {exc}"
            ) from exc
        
        # Health check: verify server is responsive
        try:
            version = utility.get_server_version()
            # Additional health check: list collections to verify full connectivity
            utility.list_collections()
        except Exception as exc:  # pragma: no cover - service guard
            raise DriverUnavailable(
                self.name,
                f"Milvus health check failed at {self._host}:{self._port}. "
                "Service may be starting or unhealthy. "
                "Check service logs and health endpoint (http://localhost:9091/healthz). "
                f"Error: {exc}"
            ) from exc

        self._utility = utility
        self._Collection = Collection
        self._FieldSchema = FieldSchema
        self._CollectionSchema = CollectionSchema
        self._DataType = DataType

    def clear(self, namespace: str) -> None:
        if self._utility is None:
            raise RuntimeError("connect() must be called before clear()")
        if self._utility.has_collection(namespace):
            self._utility.drop_collection(namespace)
        self._dimension = None

    # ------------------------------------------------------------------
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        if self._Collection is None or self._utility is None:
            raise RuntimeError("connect() must be called before upsert()")
        pending_ids: List[str] = []
        pending_vectors: List[List[float]] = []
        for identifier, vector, _metadata in items:
            if self._dimension is None:
                self._dimension = len(vector)
                self._ensure_collection(namespace, self._dimension)
            prepared = self._prepare_vector(vector)
            pending_ids.append(identifier)
            pending_vectors.append(prepared)
            if len(pending_ids) >= batch_size:
                self._flush(namespace, pending_ids, pending_vectors)
                pending_ids, pending_vectors = [], []
        if pending_ids:
            self._flush(namespace, pending_ids, pending_vectors)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        if self._Collection is None:
            raise RuntimeError("connect() must be called before search()")
        collection = self._Collection(namespace)
        collection.load()
        params = {
            "metric_type": self._milvus_metric(),
            "params": {"nprobe": 16},
        }
        prepared_query = [self._prepare_vector(query)]
        results = collection.search(
            prepared_query,
            "vector",
            param=params,
            limit=int(k),
            output_fields=[],
        )
        hits: List[Tuple[str, float]] = []
        if not results:
            return hits
        for hit in results[0]:
            score = getattr(hit, "score", getattr(hit, "distance", 0.0))
            hits.append((str(hit.id), float(score)))
        return hits[:k]

    # ------------------------------------------------------------------
    def _ensure_collection(self, namespace: str, dimension: int) -> None:
        if self._Collection is None or self._utility is None:
            raise RuntimeError("connect() must be called before upsert()")
        if self._utility.has_collection(namespace):
            return
        pk_field = self._FieldSchema(
            name="id",
            dtype=self._DataType.VARCHAR,
            is_primary=True,
            max_length=128,
        )
        vector_field = self._FieldSchema(
            name="vector",
            dtype=self._DataType.FLOAT_VECTOR,
            dim=int(dimension),
        )
        schema = self._CollectionSchema(fields=[pk_field, vector_field], description="bench")
        collection = self._Collection(namespace, schema=schema)
        index_params = {
            "index_type": "FLAT",
            "metric_type": self._milvus_metric(),
            "params": {},
        }
        collection.create_index("vector", index_params)
        collection.load()

    def _flush(
        self,
        namespace: str,
        ids: List[str],
        vectors: List[List[float]],
    ) -> None:
        collection = self._Collection(namespace)
        collection.insert([ids, vectors])
        collection.flush()

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

    def _milvus_metric(self) -> str:
        if self.metric == "l2":
            return "L2"
        if self.metric == "ip":
            return "IP"
        return "COSINE"


__all__ = ["MilvusDriver"]
