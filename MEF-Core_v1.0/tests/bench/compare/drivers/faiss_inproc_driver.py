from __future__ import annotations

import os
from typing import Dict, List, Sequence

import faiss
import numpy as np

from .base import Driver, SearchResults, UpsertItem, Vector


class FaissInProcDriver(Driver):
    """Local FAISS index using the same parameters as the HTTP service."""

    name = "faiss-inproc"

    def __init__(self) -> None:
        self._metric = os.getenv("ANN_METRIC", os.getenv("FAISS_METRIC", "cosine")).lower()
        self._index_type = os.getenv("FAISS_INDEX", "hnsw").lower()
        self._hnsw_m = int(os.getenv("HNSW_M", os.getenv("FAISS_HNSW_M", "32")))
        self._ef_search = int(os.getenv("HNSW_EFSEARCH", os.getenv("FAISS_EFSEARCH", "64")))
        self._dim: int | None = None
        self._index: faiss.IndexIDMap2 | None = None
        self._id_map: Dict[str, int] = {}
        self._reverse: Dict[int, str] = {}
        self._next_id = 1

    def connect(self) -> None:
        self._dim = None
        self._index = None
        self._id_map = {}
        self._reverse = {}
        self._next_id = 1

    def clear(self) -> None:
        self.connect()

    def upsert(self, items: List[UpsertItem]) -> None:
        if not items:
            return
        first = items[0]
        dim = len(first["values"])
        if self._dim is None:
            self._dim = dim
            self._index = self._build_index(dim)
        if self._dim != dim:
            raise ValueError("vector dimension mismatch")
        assert self._index is not None

        ids: List[int] = []
        vectors: List[List[float]] = []
        for item in items:
            if len(item["values"]) != self._dim:
                raise ValueError("vector dimension mismatch")
            identifier = str(item["id"])
            faiss_id = self._id_map.get(identifier)
            if faiss_id is None:
                faiss_id = self._next_id
                self._next_id += 1
            else:
                self._index.remove_ids(np.asarray([faiss_id], dtype="int64"))
            self._id_map[identifier] = faiss_id
            self._reverse[faiss_id] = identifier
            ids.append(faiss_id)
            vectors.append([float(value) for value in item["values"]])

        matrix = np.asarray(vectors, dtype="float32")
        self._normalise(matrix)
        ids_array = np.asarray(ids, dtype="int64")
        self._index.add_with_ids(matrix, ids_array)

    def search(self, queries: Sequence[Vector], k: int) -> SearchResults:
        if self._index is None or self._dim is None or self._index.ntotal == 0:
            return [[] for _ in queries]
        matrix = np.asarray(list(queries), dtype="float32")
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[1] != self._dim:
            raise ValueError("query dimension mismatch")
        self._normalise(matrix)
        distances, labels = self._index.search(matrix, int(k))
        hits: SearchResults = []
        for label_row, distance_row in zip(labels, distances):
            target_hits: List[tuple[str, float]] = []
            for label, score in zip(label_row, distance_row):
                if label < 0:
                    continue
                identifier = self._reverse.get(int(label))
                if identifier is None:
                    continue
                target_hits.append((identifier, float(score)))
            hits.append(target_hits)
        return hits

    def _build_index(self, dim: int) -> faiss.IndexIDMap2:
        if self._index_type == "flat":
            if self._metric == "ip":
                base: faiss.Index = faiss.IndexFlatIP(dim)
            else:
                base = faiss.IndexFlatL2(dim)
        else:
            metric = faiss.METRIC_INNER_PRODUCT if self._metric == "ip" else faiss.METRIC_L2
            base = faiss.IndexHNSWFlat(dim, int(self._hnsw_m), metric)
            base.hnsw.efSearch = int(self._ef_search)
        return faiss.IndexIDMap2(base)

    def _normalise(self, matrix: np.ndarray) -> None:
        if self._metric == "ip" and matrix.size:
            faiss.normalize_L2(matrix)


__all__ = ["FaissInProcDriver"]
