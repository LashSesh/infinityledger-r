from __future__ import annotations

import os
import threading
from typing import Dict, List

import faiss
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, Field


class VectorPayload(BaseModel):
    id: str = Field(..., min_length=1)
    values: List[float]


class UpsertRequest(BaseModel):
    vectors: List[VectorPayload]


class SearchRequest(BaseModel):
    queries: List[List[float]]
    k: int = Field(..., ge=1)


def _normalise(metric: str, array: np.ndarray) -> None:
    if metric == "ip" and array.size:
        faiss.normalize_L2(array)


class _FaissState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._metric = os.getenv("FAISS_METRIC", "l2").lower()
        self._index_type = os.getenv("FAISS_INDEX", "hnsw").lower()
        self._hnsw_m = int(os.getenv("FAISS_HNSW_M", "32"))
        self._ef_search = int(os.getenv("FAISS_EFSEARCH", "64"))
        self._dim: int | None = None
        self._index: faiss.IndexIDMap2 | None = None
        self._id_map: Dict[str, int] = {}
        self._reverse: Dict[int, str] = {}
        self._next_id = 1

    def clear(self) -> None:
        with self._lock:
            self._dim = None
            self._index = None
            self._id_map.clear()
            self._reverse.clear()
            self._next_id = 1

    def upsert(self, payload: UpsertRequest) -> None:
        with self._lock:
            if not payload.vectors:
                return
            first = payload.vectors[0]
            dim = len(first.values)
            if dim == 0:
                raise HTTPException(status_code=400, detail="vectors must have non-zero dimension")
            if self._dim is None:
                self._dim = dim
                self._index = self._build_index(dim)
            if self._dim != dim:
                raise HTTPException(status_code=400, detail="vector dimension mismatch")
            assert self._index is not None

            ids: List[int] = []
            vectors: List[List[float]] = []
            for record in payload.vectors:
                if len(record.values) != self._dim:
                    raise HTTPException(status_code=400, detail="vector dimension mismatch")
                faiss_id = self._id_map.get(record.id)
                if faiss_id is None:
                    faiss_id = self._next_id
                    self._next_id += 1
                else:
                    self._index.remove_ids(np.array([faiss_id], dtype="int64"))
                self._id_map[record.id] = faiss_id
                self._reverse[faiss_id] = record.id
                ids.append(faiss_id)
                vectors.append([float(value) for value in record.values])

            matrix = np.asarray(vectors, dtype="float32")
            _normalise(self._metric, matrix)
            ids_array = np.asarray(ids, dtype="int64")
            self._index.add_with_ids(matrix, ids_array)

    def search(self, payload: SearchRequest) -> Dict[str, List[List[Dict[str, float]]]]:
        with self._lock:
            if self._index is None or self._dim is None or self._index.ntotal == 0:
                return {"hits": [[] for _ in payload.queries]}
            queries = np.asarray(payload.queries, dtype="float32")
            if queries.ndim == 1:
                queries = queries.reshape(1, -1)
            if queries.shape[1] != self._dim:
                raise HTTPException(status_code=400, detail="query dimension mismatch")
            _normalise(self._metric, queries)
            distances, labels = self._index.search(queries, int(payload.k))
            hits: List[List[Dict[str, float]]] = []
            for query_labels, query_distances in zip(labels, distances):
                results: List[Dict[str, float]] = []
                for label, score in zip(query_labels, query_distances):
                    if label < 0:
                        continue
                    identifier = self._reverse.get(int(label))
                    if identifier is None:
                        continue
                    results.append({"id": identifier, "score": float(score)})
                hits.append(results)
            return {"hits": hits}

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


state = _FaissState()
app = FastAPI(default_response_class=ORJSONResponse)


@app.post("/clear")
def clear_vectors() -> Dict[str, str]:
    state.clear()
    return {"status": "cleared"}


@app.post("/upsert")
def upsert_vectors(request: UpsertRequest) -> Dict[str, str]:
    state.upsert(request)
    return {"status": "ok", "count": len(request.vectors)}


@app.post("/search")
def search_vectors(request: SearchRequest) -> Dict[str, List[List[Dict[str, float]]]]:
    return state.search(request)
