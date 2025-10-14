"""FAISS-backed brute force baseline driver for recall ground truth."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:  # pragma: no cover - optional dependency in CI
    import faiss  # type: ignore
except Exception:  # pragma: no cover - gracefully handle missing faiss
    faiss = None

from .base import UpsertItem, Vector, VectorStoreDriver


class FaissBaselineDriver(VectorStoreDriver):
    """Brute-force exact nearest-neighbour search implemented with FAISS."""

    name = "faiss-baseline"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)
        self._index: Optional["faiss.Index"] = None
        self._ids: List[str] = []
        self._vectors: List[np.ndarray] = []
        self._dimension: Optional[int] = None
        self._use_faiss = faiss is not None

    # ------------------------------------------------------------------
    def connect(self) -> None:
        if not self._use_faiss:
            # fall back to NumPy-based brute force if faiss is unavailable
            return
        # lazily create the index when the first batch arrives

    def clear(self, namespace: str) -> None:  # pragma: no cover - trivial
        self._index = None
        self._ids = []
        self._vectors = []
        self._dimension = None

    # ------------------------------------------------------------------
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        batch: List[np.ndarray] = []
        ids: List[str] = []
        for identifier, vector, _metadata in items:
            prepared = self._prepare_vector(vector)
            if prepared is None:
                continue
            ids.append(identifier)
            batch.append(prepared)
        if not batch:
            return

        matrix = np.vstack(batch)
        self._ids.extend(ids)
        self._vectors.extend(batch)
        if self._use_faiss:
            if self._index is None:
                if self.metric in {"cosine", "ip"}:
                    self._index = faiss.IndexFlatIP(matrix.shape[1])
                else:
                    self._index = faiss.IndexFlatL2(matrix.shape[1])
            self._index.add(matrix)

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        vector = self._prepare_query(query)
        if vector is None:
            return []
        if self._use_faiss and self._index is not None:
            distances, indices = self._index.search(vector[np.newaxis, :], min(k, len(self._ids)))
            hits: List[Tuple[str, float]] = []
            for score, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(self._ids):
                    continue
                hits.append((self._ids[idx], float(score)))
            return hits

        if not self._vectors:
            return []
        matrix = np.vstack(self._vectors)
        if self.metric in {"cosine", "ip"}:
            scores = matrix @ vector
        else:
            diff = matrix - vector
            scores = -np.sum(diff * diff, axis=1)
        order = np.argsort(scores)[::-1][: min(k, len(self._ids))]
        return [(self._ids[idx], float(scores[idx])) for idx in order]

    # ------------------------------------------------------------------
    def _prepare_vector(self, vector: Sequence[float]) -> Optional[np.ndarray]:
        array = np.asarray(vector, dtype="float32")
        if array.ndim != 1:
            return None
        if self._dimension is None:
            self._dimension = array.shape[0]
        if array.shape[0] != self._dimension:
            raise ValueError(
                f"dimension mismatch: expected {self._dimension}, received {array.shape[0]}"
            )
        return self._normalise(array)

    def _prepare_query(self, vector: Sequence[float]) -> Optional[np.ndarray]:
        array = np.asarray(vector, dtype="float32")
        if self._dimension is not None and array.shape[0] != self._dimension:
            raise ValueError(
                f"query dimension mismatch: expected {self._dimension}, received {array.shape[0]}"
            )
        if self._dimension is None:
            self._dimension = array.shape[0]
        return self._normalise(array)

    def _normalise(self, array: np.ndarray) -> np.ndarray:
        if self.metric in {"cosine", "ip"}:
            norm = float(np.linalg.norm(array))
            if norm == 0.0:
                return array
            return array / norm
        return array
