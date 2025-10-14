"""Dataclass representations of the SPEC-002 blueprint."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Spec:
    """Metadata describing the blueprint specification."""

    id: str
    title: str
    version: str
    date: str
    owners: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Spec":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            version=str(data.get("version", "")),
            date=str(data.get("date", "")),
            owners=list(data.get("owners", [])),
            goals=list(data.get("goals", [])),
        )


@dataclass(frozen=True)
class Component:
    """Component entry from the blueprint."""

    name: str
    type: str
    deps: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Component":
        known = {"name", "type", "deps", "responsibilities"}
        extras = {key: value for key, value in data.items() if key not in known}
        deps = data.get("deps")
        responsibilities = data.get("responsibilities")
        return cls(
            name=str(data.get("name", "")),
            type=str(data.get("type", "")),
            deps=list(deps) if isinstance(deps, list) else None,
            responsibilities=list(responsibilities) if isinstance(responsibilities, list) else None,
            extras=extras,
        )


@dataclass(frozen=True)
class API:
    """API surface description."""

    rest: List[str]
    grpc: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "API":
        rest = data.get("rest", [])
        grpc = data.get("grpc", {})
        return cls(rest=list(rest), grpc=dict(grpc))


@dataclass(frozen=True)
class Storage:
    """Storage configuration."""

    fs_root: str
    s3: Dict[str, Any]
    layout: Dict[str, Any]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Storage":
        return cls(
            fs_root=str(data.get("fs_root", "")),
            s3=dict(data.get("s3", {})),
            layout=dict(data.get("layout", {})),
        )


@dataclass(frozen=True)
class Blueprint:
    """Top-level blueprint model."""

    spec: Spec
    priorities: Dict[str, List[str]]
    components: List[Component]
    storage: Storage
    distance: Dict[str, Any]
    schemas: Dict[str, Any]
    api: API
    index_backends: Dict[str, Any]
    consistency: Dict[str, Any]
    merkaba_gate: Dict[str, Any]
    workflows: Dict[str, Any]
    security: Dict[str, Any]
    observability: Dict[str, Any]
    config: Dict[str, Any]
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Blueprint":
        known = {
            "spec",
            "priorities",
            "components",
            "storage",
            "distance",
            "schemas",
            "api",
            "index_backends",
            "consistency",
            "merkaba_gate",
            "workflows",
            "security",
            "observability",
            "config",
        }
        extras = {key: value for key, value in data.items() if key not in known}
        components = [Component.from_dict(item) for item in data.get("components", [])]
        return cls(
            spec=Spec.from_dict(data.get("spec", {})),
            priorities={key: list(value) for key, value in data.get("priorities", {}).items()},
            components=components,
            storage=Storage.from_dict(data.get("storage", {})),
            distance=dict(data.get("distance", {})),
            schemas=dict(data.get("schemas", {})),
            api=API.from_dict(data.get("api", {})),
            index_backends=dict(data.get("index_backends", {})),
            consistency=dict(data.get("consistency", {})),
            merkaba_gate=dict(data.get("merkaba_gate", {})),
            workflows=dict(data.get("workflows", {})),
            security=dict(data.get("security", {})),
            observability=dict(data.get("observability", {})),
            config=dict(data.get("config", {})),
            extras=extras,
        )


__all__ = ["Spec", "Component", "API", "Storage", "Blueprint"]
