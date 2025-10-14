from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

Vector = Sequence[float]
UpsertItem = Dict[str, object]
SearchResults = List[List[Tuple[str, float]]]


class Driver:
    """Abstract interface shared by compare benchmark drivers."""

    name: str = "driver"

    def connect(self) -> None:  # pragma: no cover - interface method
        raise NotImplementedError

    def clear(self) -> None:  # pragma: no cover - interface method
        raise NotImplementedError

    def upsert(self, items: List[UpsertItem]) -> None:  # pragma: no cover - interface method
        raise NotImplementedError

    def search(self, queries: Sequence[Vector], k: int) -> SearchResults:  # pragma: no cover - interface method
        raise NotImplementedError


__all__ = ["Driver", "UpsertItem", "Vector", "SearchResults"]
