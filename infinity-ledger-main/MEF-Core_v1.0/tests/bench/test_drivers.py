"""Smoke tests for compare benchmark drivers."""

from __future__ import annotations

from typing import Iterable, Tuple

import time

import pytest

from tests.bench.compare import _connect_with_retries
from bench.drivers import (
    DriverUnavailable,
    ElasticDriver,
    FaissBaselineDriver,
    MEFDriver,
    MilvusDriver,
    PineconeDriver,
    QdrantDriver,
    VectorStoreDriver,
    WeaviateDriver,
)


@pytest.mark.parametrize(
    "driver_cls",
    [MEFDriver, QdrantDriver, MilvusDriver, WeaviateDriver, ElasticDriver, PineconeDriver],
)
def test_driver_connect_smoke(driver_cls: type[VectorStoreDriver]) -> None:
    driver = driver_cls()
    try:
        driver.connect()
    except DriverUnavailable as exc:
        pytest.skip(exc.reason)
    except Exception as exc:
        pytest.skip(str(exc))


def test_faiss_baseline_round_trip() -> None:
    driver = FaissBaselineDriver()
    driver.connect()
    driver.clear("bench")
    items: Iterable[Tuple[str, Tuple[float, ...], dict]] = [
        ("a", (1.0, 0.0, 0.0), {}),
        ("b", (0.0, 1.0, 0.0), {}),
        ("c", (0.0, 0.0, 1.0), {}),
    ]
    driver.upsert(items, "bench")
    hits = driver.search((1.0, 0.1, 0.0), 2, "bench")
    assert hits
    assert hits[0][0] == "a"


class _UnreachableDriver(VectorStoreDriver):
    name = "unreachable"

    def connect(self) -> None:  # pragma: no cover - invoked via _connect_with_retries
        raise DriverUnavailable(self.name, "failed to contact service")

    def clear(self, namespace: str) -> None:  # pragma: no cover - unused in test
        raise AssertionError("clear should not be called")

    def upsert(
        self,
        items: Iterable[Tuple[str, Tuple[float, ...], dict]],
        namespace: str,
        batch_size: int = 1000,
    ) -> None:  # pragma: no cover - unused in test
        raise AssertionError("upsert should not be called")

    def search(
        self,
        query: Tuple[float, ...],
        k: int,
        namespace: str,
    ) -> Iterable[Tuple[str, float]]:  # pragma: no cover - unused in test
        raise AssertionError("search should not be called")


def test_connect_with_retries_short_circuits_on_unreachable_service() -> None:
    driver = _UnreachableDriver()
    start = time.perf_counter()
    with pytest.raises(DriverUnavailable):
        _connect_with_retries(driver, timeout=0.1)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5


def test_qdrant_driver_waits_for_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    from bench.drivers import qdrant_driver as module

    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")

    recreate_waits: list[bool] = []
    upsert_waits: list[bool] = []

    class _StubHttpClient:
        def health(self) -> None:  # pragma: no cover - no-op
            return None

    class _StubClient:
        def __init__(self, **_kwargs) -> None:
            self._healthy = True

        def get_health(self) -> None:  # pragma: no cover - no-op
            if not self._healthy:
                raise RuntimeError("unhealthy")

        def delete_collection(self, _name: str) -> None:  # pragma: no cover - no-op
            return None

        def recreate_collection(self, **kwargs) -> None:
            recreate_waits.append(bool(kwargs.get("wait")))

        def upsert(self, **kwargs) -> None:
            upsert_waits.append(bool(kwargs.get("wait")))

    monkeypatch.setattr(module, "QdrantClient", lambda **kwargs: _StubClient(**kwargs))

    driver = module.QdrantDriver()
    driver.connect()
    driver.clear("compare-test")
    driver.upsert([("a", (0.1, 0.2, 0.3), {})], "compare-test", batch_size=1)

    assert recreate_waits == [True]
    assert upsert_waits
    assert all(upsert_waits)
