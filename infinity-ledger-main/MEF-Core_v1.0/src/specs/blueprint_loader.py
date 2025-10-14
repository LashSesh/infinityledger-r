"""Utilities for loading and validating MEF-Core evolution blueprints."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None
from .blueprint_models import Blueprint


REQUIRED_TOP_LEVEL_KEYS = (
    "spec",
    "priorities",
    "components",
    "storage",
    "api",
    "index_backends",
    "consistency",
    "merkaba_gate",
    "workflows",
    "config",
)


class BlueprintValidationError(RuntimeError):
    """Raised when a blueprint fails validation."""


class BlueprintSchemaError(BlueprintValidationError):
    """Raised when the blueprint does not conform to the JSON schema."""


@dataclass(frozen=True)
class BlueprintDocument:
    """Container for a validated blueprint and its derived artifacts."""

    model: Blueprint
    raw: Dict[str, Any]
    normalized_yaml: str
    spec_hash: str


def _validate_schema(data: Dict[str, Any]) -> None:
    """Validate blueprint data against the required structural constraints."""

    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in data]
    if missing:
        raise BlueprintSchemaError(f"Missing required top-level keys: {', '.join(sorted(missing))}")

    if not isinstance(data["spec"], dict):
        raise BlueprintSchemaError("spec must be a mapping")
    spec_missing = [field for field in ("id", "title", "version", "date") if field not in data["spec"]]
    if spec_missing:
        raise BlueprintSchemaError(f"spec missing fields: {', '.join(sorted(spec_missing))}")

    if not isinstance(data["priorities"], dict):
        raise BlueprintSchemaError("priorities must be a mapping")
    for field in ("must", "should", "could"):
        if field not in data["priorities"]:
            raise BlueprintSchemaError(f"priorities missing '{field}' list")

    components = data["components"]
    if not isinstance(components, list):
        raise BlueprintSchemaError("components must be a list")
    for index, component in enumerate(components):
        if not isinstance(component, dict):
            raise BlueprintSchemaError(f"components[{index}] must be a mapping")
        for field in ("name", "type"):
            if field not in component:
                raise BlueprintSchemaError(f"components[{index}] missing '{field}'")

    storage = data["storage"]
    if not isinstance(storage, dict):
        raise BlueprintSchemaError("storage must be a mapping")
    for field in ("fs_root", "s3", "layout"):
        if field not in storage:
            raise BlueprintSchemaError(f"storage missing '{field}'")

    api = data["api"]
    if not isinstance(api, dict):
        raise BlueprintSchemaError("api must be a mapping")
    for field in ("rest", "grpc"):
        if field not in api:
            raise BlueprintSchemaError(f"api missing '{field}'")

    backends = data["index_backends"]
    if not isinstance(backends, dict):
        raise BlueprintSchemaError("index_backends must be a mapping")
    for field in ("hnsw", "faiss"):
        if field not in backends:
            raise BlueprintSchemaError(f"index_backends missing '{field}'")

    if not isinstance(data["consistency"], dict):
        raise BlueprintSchemaError("consistency must be a mapping")

    merkaba_gate = data["merkaba_gate"]
    if not isinstance(merkaba_gate, dict):
        raise BlueprintSchemaError("merkaba_gate must be a mapping")
    for field in ("graph", "on_fail"):
        if field not in merkaba_gate:
            raise BlueprintSchemaError(f"merkaba_gate missing '{field}'")

    workflows = data["workflows"]
    if not isinstance(workflows, dict):
        raise BlueprintSchemaError("workflows must be a mapping")
    for field in ("upsert", "query", "rebuild"):
        if field not in workflows:
            raise BlueprintSchemaError(f"workflows missing '{field}'")

    config = data["config"]
    if not isinstance(config, dict):
        raise BlueprintSchemaError("config must be a mapping")
    if "env" not in config:
        raise BlueprintSchemaError("config missing 'env'")


def _normalize_yaml(data: Dict[str, Any]) -> str:
    """Render a normalized YAML string with sorted keys."""

    if yaml is not None:
        return yaml.safe_dump(data, sort_keys=True, allow_unicode=True, default_flow_style=False)
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2)


def _load_yaml(text: str) -> Dict[str, Any]:
    """Parse YAML (or JSON) into a dictionary."""

    if yaml is not None:
        loaded = yaml.safe_load(text) or {}
    else:
        try:
            loaded = json.loads(text or "{}")
        except json.JSONDecodeError as exc:  # pragma: no cover - indicates missing dependency
            raise BlueprintValidationError(
                "PyYAML is required to parse non-JSON blueprints"
            ) from exc
    if not isinstance(loaded, dict):
        raise BlueprintValidationError("Blueprint root must be a mapping")
    return loaded


def _compute_hash(normalized_yaml: str) -> str:
    """Compute the BLAKE3 hash of the normalized YAML representation."""

    try:
        from blake3 import blake3  # type: ignore
    except Exception:
        import hashlib

        return hashlib.blake2b(normalized_yaml.encode("utf-8"), digest_size=32).hexdigest()
    return blake3(normalized_yaml.encode("utf-8")).hexdigest()


def load_blueprint(path: Path | str) -> BlueprintDocument:
    """Load, validate, and normalize a blueprint from disk."""

    blueprint_path = Path(path)
    if not blueprint_path.exists():
        raise FileNotFoundError(f"Blueprint file not found: {blueprint_path}")

    with blueprint_path.open("r", encoding="utf-8") as fp:
        raw_yaml = fp.read()

    data = _load_yaml(raw_yaml)

    _validate_schema(data)

    model = Blueprint.from_dict(data)

    normalized_yaml = _normalize_yaml(data)
    spec_hash = _compute_hash(normalized_yaml)

    return BlueprintDocument(model=model, raw=data, normalized_yaml=normalized_yaml, spec_hash=spec_hash)


__all__ = [
    "Blueprint",
    "BlueprintDocument",
    "BlueprintValidationError",
    "BlueprintSchemaError",
    "load_blueprint",
]
