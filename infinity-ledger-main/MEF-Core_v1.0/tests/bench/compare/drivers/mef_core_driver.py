from __future__ import annotations

import os
from typing import Dict, List, Sequence

from vector_db.providers import HNSWProvider

from .base import Driver, SearchResults, UpsertItem, Vector


class MEFCoreDriver(Driver):
    """In-process driver that exercises the MEF ANN provider directly."""

    name = "mef-core"

    def __init__(self) -> None:
        self._metric = os.getenv("ANN_METRIC", "cosine").lower()
        self._hnsw_m = int(os.getenv("HNSW_M", os.getenv("FAISS_HNSW_M", "32")))
        self._ef_construction = int(os.getenv("HNSW_EFCONSTRUCTION", "200"))
        self._ef_search = int(os.getenv("HNSW_EFSEARCH", os.getenv("FAISS_EFSEARCH", "64")))
        self._provider: HNSWProvider | None = None
        self._records: Dict[str, Dict[str, object]] = {}

    def connect(self) -> None:
        self._provider = self._build_provider()
        self._records = {}

    def clear(self) -> None:
        self._provider = self._build_provider()
        self._records = {}

    def upsert(self, items: List[UpsertItem]) -> None:
        if self._provider is None:
            raise RuntimeError("connect() must be called before upsert()")
        for item in items:
            identifier = str(item["id"])
            values = [float(value) for value in item["values"]]
            metadata = dict(item.get("metadata", {}))
            record = {
                "vector": values,
                "metadata": metadata,
                "epoch": int(item.get("epoch", 1)),
            }
            self._records[identifier] = record
            self._provider.upsert(identifier, record)

    def search(self, queries: Sequence[Vector], k: int) -> SearchResults:
        if self._provider is None:
            raise RuntimeError("connect() must be called before search()")
        results: SearchResults = []
        for query in queries:
            hits = self._provider.search(
                list(query),
                self._records,
                top_k=int(k),
                ef_search=self._ef_search,
            )
            results.append([(identifier, float(score)) for identifier, score in hits])
        return results

    def _build_provider(self) -> HNSWProvider:
        return HNSWProvider(
            m=self._hnsw_m,
            ef_construction=self._ef_construction,
            ef_search=self._ef_search,
            metric=self._metric,
        )


__all__ = ["MEFCoreDriver"]
