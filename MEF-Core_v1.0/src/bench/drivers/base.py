"""Common interfaces for vector store benchmark drivers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

Vector = Sequence[float]
UpsertItem = Tuple[str, Vector, Optional[Mapping[str, Any]]]


class DriverUnavailable(RuntimeError):
    """Raised when a benchmark target cannot be reached or configured."""

    def __init__(self, name: str, reason: str) -> None:
        super().__init__(reason)
        self.name = name
        self.reason = reason

    def as_dict(self) -> Dict[str, str]:
        """Return a JSON-serialisable payload describing the skip."""

        return {"name": self.name, "skipped": True, "reason": self.reason}


class VectorStoreDriver:
    """Abstract interface every benchmark target driver must implement."""

    name: str = "vector-store"
    metric: str

    def __init__(self, metric: str = "cosine") -> None:
        self.metric = metric.lower()

    # ------------------------------------------------------------------
    # lifecycle hooks
    def connect(self) -> None:
        """Connect to the service or initialise the underlying client."""

        raise NotImplementedError

    def clear(self, namespace: str) -> None:
        """Drop or empty the target namespace/collection/index."""

        raise NotImplementedError

    # ------------------------------------------------------------------
    # mutation & search
    def upsert(
        self,
        items: Iterable[UpsertItem],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:
        """Insert/update vectors + metadata in batches."""

        raise NotImplementedError

    def search(self, query: Vector, k: int, namespace: str) -> Sequence[Tuple[str, float]]:
        """Return ``[(id, score)]`` with comparable scoring to the metric."""

        raise NotImplementedError
