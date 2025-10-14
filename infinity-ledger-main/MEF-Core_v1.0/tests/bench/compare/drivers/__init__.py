from __future__ import annotations

from typing import Dict, Type

from .base import Driver
from .faiss_http_driver import FaissHTTPDriver
from .faiss_inproc_driver import FaissInProcDriver
from .mef_core_driver import MEFCoreDriver
from .mef_http_driver import MEFHTTPDriver

DRIVER_REGISTRY: Dict[str, Type[Driver]] = {
    MEFCoreDriver.name: MEFCoreDriver,
    FaissInProcDriver.name: FaissInProcDriver,
    MEFHTTPDriver.name: MEFHTTPDriver,
    FaissHTTPDriver.name: FaissHTTPDriver,
}


def get_driver(name: str) -> Type[Driver]:
    try:
        return DRIVER_REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise KeyError(f"unknown driver: {name}") from exc


__all__ = [
    "Driver",
    "DRIVER_REGISTRY",
    "FaissHTTPDriver",
    "FaissInProcDriver",
    "MEFCoreDriver",
    "MEFHTTPDriver",
    "get_driver",
]
