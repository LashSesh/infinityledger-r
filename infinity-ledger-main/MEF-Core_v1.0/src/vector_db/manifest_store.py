"""Manifest and persistence management for vector index artefacts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

import boto3

from .index_manager import CollectionState


@dataclass
class PersistenceConfig:
    """Configuration for persisting artefacts to an external service."""

    provider: Optional[str] = None
    bucket: Optional[str] = None
    prefix: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "PersistenceConfig":
        payload = payload or {}
        return cls(
            provider=payload.get("provider") or payload.get("type"),
            bucket=payload.get("bucket"),
            prefix=payload.get("prefix"),
        )

    def is_s3(self) -> bool:
        return (self.provider or "").lower() == "s3" and bool(self.bucket)


@dataclass
class Manifest:
    """Representation of the manifest metadata."""

    collections: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collections": self.collections,
            "persistence": {
                "provider": self.persistence.provider,
                "bucket": self.persistence.bucket,
                "prefix": self.persistence.prefix,
            },
        }

    @classmethod
    def from_dict(cls, payload: Optional[Dict[str, Any]]) -> "Manifest":
        payload = payload or {}
        persistence = PersistenceConfig.from_dict(payload.get("persistence"))
        return cls(
            collections=dict(payload.get("collections", {})),
            persistence=persistence,
        )


class ManifestStore:
    """Manage manifest metadata and persistence for vector index artefacts."""

    def __init__(
        self,
        base_path: Union[str, Path],
        *,
        manifest_data: Optional[Dict[str, Any]] = None,
        persistence_config: Optional[Dict[str, Any]] = None,
        s3_client: Optional[Any] = None,
    ) -> None:
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        self.manifest_path = self.base_path / "manifest.json"
        self.manifest = self._load_manifest(manifest_data)

        if persistence_config:
            self.manifest.persistence = PersistenceConfig.from_dict(persistence_config)

        self._s3_client = s3_client

    # ------------------------------------------------------------------
    def persist_state(
        self,
        collection: str,
        state: CollectionState,
        *,
        epoch: int,
        artefacts: Optional[Dict[str, Union[str, Path]]] = None,
    ) -> Path:
        """Persist a collection state and optional artefacts under a versioned path."""

        version_dir = self._version_path(collection, epoch)
        version_dir.mkdir(parents=True, exist_ok=True)

        state_path = version_dir / "index.json"
        with state_path.open("w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=2, sort_keys=True)

        self.manifest.collections[collection] = {
            "latest_epoch": epoch,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "path": str(version_dir.relative_to(self.base_path)),
        }
        self._save_manifest()

        artefacts = artefacts or {}
        uploaded_files = [state_path, self.manifest_path]
        for name, file_path in artefacts.items():
            path = version_dir / name
            src = Path(file_path)
            if src.is_file():
                path.write_bytes(src.read_bytes())
                uploaded_files.append(path)

        self._sync_to_s3(uploaded_files)
        return version_dir

    def get_manifest(self) -> Manifest:
        return self.manifest

    def set_active_epoch(self, collection: str, epoch: int) -> None:
        """Mark an epoch as active for a collection and persist the manifest."""

        entry = self.manifest.collections.setdefault(collection, {})
        entry["active_epoch"] = int(epoch)
        entry["activated_at"] = datetime.utcnow().isoformat() + "Z"
        self._save_manifest()
        self._sync_to_s3([self.manifest_path])

    # ------------------------------------------------------------------
    def _version_path(self, collection: str, epoch: int) -> Path:
        return self.base_path / collection / f"v{int(epoch)}"

    def _load_manifest(self, manifest_data: Optional[Dict[str, Any]]) -> Manifest:
        if manifest_data:
            return Manifest.from_dict(manifest_data)
        if self.manifest_path.exists():
            with self.manifest_path.open("r", encoding="utf-8") as fh:
                return Manifest.from_dict(json.load(fh))
        return Manifest()

    def _save_manifest(self) -> None:
        with self.manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(self.manifest.to_dict(), fh, indent=2, sort_keys=True)

    def _sync_to_s3(self, files: Iterable[Path]) -> None:
        if not files:
            return

        config = self.manifest.persistence
        if not config.is_s3():
            return

        client = self._s3_client
        if client is None:
            client = boto3.client("s3")
            self._s3_client = client

        prefix = config.prefix.strip("/") if config.prefix else ""
        for file_path in files:
            relative = file_path.relative_to(self.base_path)
            key = f"{prefix}/{relative}" if prefix else str(relative)
            client.upload_file(str(file_path), config.bucket, key)
