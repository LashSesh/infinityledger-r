"""Utilities for managing persisted vector collections and index metadata."""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

import numpy as np

from .providers import IndexProvider, get_provider, PROVIDERS

VECTOR_DB_PATH = Path(
    os.getenv("VECTOR_DB_PATH", Path.home() / "mef" / "vector_db")
)


logger = logging.getLogger(__name__)


@dataclass
class VectorRecord:
    """Representation of a single vector record."""

    id: str
    values: Sequence[float]
    metadata: MutableMapping[str, Any]
    epoch: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert the record to a serialisable dictionary."""
        return {
            "id": self.id,
            "vector": list(self.values),
            "metadata": dict(self.metadata),
            "epoch": self.epoch,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "VectorRecord":
        return cls(
            id=payload["id"],
            values=list(payload.get("vector", [])),
            metadata=dict(payload.get("metadata", {})),
            epoch=payload.get("epoch"),
        )


@dataclass
class CollectionState:
    """In-memory representation of a collection."""

    vectors: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    indexes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vectors": self.vectors,
            "indexes": self.indexes,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "CollectionState":
        return cls(
            vectors=dict(payload.get("vectors", {})),
            indexes=dict(payload.get("indexes", {})),
        )


class IndexManager:
    """Manage persisted vector sets and related index metadata."""

    _VOLATILE_KEY_NAMES: Tuple[str, ...] = (
        "timestamp",
        "created",
        "created_at",
        "updated",
        "updated_at",
        "stored_at",
        "ingested_at",
        "acquired_at",
        "activated_at",
        "generated_at",
        "refreshed_at",
        "expires_at",
        "expiration",
        "last_updated",
        "last_modified",
    )
    _VOLATILE_KEY_SUFFIXES: Tuple[str, ...] = ("_ts", "_timestamp")

    def __init__(self, base_path: Optional[Union[str, Path]] = None) -> None:
        self.base_path = Path(base_path or VECTOR_DB_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.collections: Dict[str, CollectionState] = {}
        self.collection_providers: Dict[str, str] = {}
        self._provider_instances: Dict[str, IndexProvider] = {}
        self._ephemeral_provider_cache: "OrderedDict[Tuple[str, str, Optional[str], Optional[str], Optional[int]], IndexProvider]" = OrderedDict()
        self._ephemeral_cache_limit = int(os.getenv("INDEX_EPHEMERAL_CACHE", "6"))
        self._last_search_plan: Dict[str, Any] = {}
        self._index_status: Dict[str, Dict[str, Any]] = {}
        self._load_existing_state()

    # ------------------------------------------------------------------
    # public API
    def upsert_vectors(
        self,
        collection: str,
        records: Sequence[Union[VectorRecord, Dict[str, Any]]],
        *,
        epoch: Optional[int] = None,
        indexes: Optional[Dict[str, Any]] = None,
    ) -> CollectionState:
        """Insert or update vector records for a collection.

        Parameters
        ----------
        collection:
            Name of the collection to mutate.
        records:
            Iterable of :class:`VectorRecord` (or raw dictionaries) to persist.
        epoch:
            Epoch that should be attached to the upsert operation if the
            individual records do not specify one.
        indexes:
            Optional index metadata to merge into the collection state.
        """

        if not records:
            return self.collections.get(collection, CollectionState())

        state = self.collections.setdefault(collection, CollectionState())

        provider = self._ensure_provider(collection)

        mutated = False

        for item in records:
            record = self._ensure_record(item)
            record_epoch = record.epoch if record.epoch is not None else epoch
            if record_epoch is None:
                raise ValueError("Epoch must be provided either per record or as an argument.")

            existing = state.vectors.get(record.id)
            deterministic_updated_at = None
            if existing:
                deterministic_updated_at = existing.get("updated_at")
            if not deterministic_updated_at:
                deterministic_updated_at = f"epoch-{int(record_epoch)}"

            metadata = self._canonicalize_metadata(
                dict(record.metadata), context=f"{collection}:{record.id}"
            )

            state.vectors[record.id] = {
                "vector": list(record.values),
                "metadata": metadata,
                "epoch": int(record_epoch),
                "updated_at": deterministic_updated_at,
            }
            provider.upsert(record.id, state.vectors[record.id])
            mutated = True

        if indexes:
            state.indexes.update(indexes)

        state.indexes.setdefault("provider", provider.name)
        if hasattr(provider, "_config"):
            state.indexes.setdefault("provider_params", dict(getattr(provider, "_config")))
        if mutated:
            state.indexes["proof_version"] = int(state.indexes.get("proof_version", 0)) + 1
        self._persist_collection(collection, state)
        self._index_status.pop(collection, None)
        return state

    def delete_vectors(
        self,
        collection: str,
        vector_ids: Iterable[str],
        *,
        epoch: Optional[int] = None,
    ) -> CollectionState:
        """Delete vectors from a collection and persist the state."""

        state = self.collections.setdefault(collection, CollectionState())
        removed = False
        for vector_id in vector_ids:
            if vector_id in state.vectors:
                removed = True
                del state.vectors[vector_id]
        provider = self._ensure_provider(collection)

        if removed:
            # Track the epoch at which deletions happened for auditing purposes.
            if epoch is not None:
                state.indexes.setdefault("deletion_epochs", []).append(int(epoch))
            for vector_id in vector_ids:
                provider.delete(vector_id)
            state.indexes["proof_version"] = int(state.indexes.get("proof_version", 0)) + 1
            self._persist_collection(collection, state)
        return state

    def get_collection_state(self, collection: str) -> CollectionState:
        """Retrieve the current in-memory state for a collection."""

        return self.collections.setdefault(collection, CollectionState())

    def search_vectors(
        self,
        collection: str,
        query: Sequence[float],
        *,
        top_k: int = 5,
        provider: Optional[str] = None,
        mode: Optional[str] = None,
        ef_search: Optional[int] = None,
    ) -> Sequence[Dict[str, Any]]:
        """Run a similarity search without mutating collection state."""

        state = self.collections.get(collection)
        if state is None or not state.vectors:
            logger.debug(
                "search requested for empty collection; collection=%s has_state=%s",
                collection,
                state is not None,
            )
            return []

        metric_name = state.indexes.get("metric", "cosine")
        use_exact = (mode or "").lower() == "exact"
        default_provider_name = (
            self.collection_providers.get(collection)
            or state.indexes.get("provider")
            or list(PROVIDERS.keys())[0]
        )
        provider_name_used = provider or default_provider_name

        if use_exact:
            total_start = time.perf_counter()
            ordered_ids = sorted(state.vectors.keys())
            matrix = np.asarray(
                [state.vectors[vector_id]["vector"] for vector_id in ordered_ids],
                dtype="float32",
            )
            query_array = np.asarray(list(query), dtype="float32")

            if metric_name == "cosine":
                dot = matrix @ query_array
                norms = np.linalg.norm(matrix, axis=1)
                query_norm = float(np.linalg.norm(query_array)) or 1.0
                denom = norms * query_norm
                with np.errstate(divide="ignore", invalid="ignore"):
                    scores = np.divide(dot, denom, out=np.zeros_like(dot), where=denom != 0)
            else:
                diff = matrix - query_array
                scores = -np.sum(diff * diff, axis=1)

            rank_start = time.perf_counter()
            order = np.lexsort((np.asarray(ordered_ids), -scores))
            sorted_indices = order[:top_k]
            rank_ms = (time.perf_counter() - rank_start) * 1000.0
            total_ms = (time.perf_counter() - total_start) * 1000.0

            provider_version = "1.0"
            self._last_search_plan = {
                "plan": "exact",
                "index": "bruteforce",
                "params": {"metric": metric_name},
                "counters": {
                    "visited": int(matrix.shape[0]),
                    "scanned": int(matrix.shape[0]),
                },
                "timings_ms": {
                    "distance": total_ms - rank_ms,
                    "rank": rank_ms,
                    "total": total_ms,
                },
                "provider_used": {
                    "name": provider_name_used or "exact",
                    "version": provider_version,
                },
            }

            ranked = []
            for idx in sorted_indices:
                vector_id = ordered_ids[int(idx)]
                payload = state.vectors[vector_id]
                ranked.append(
                    {
                        "id": vector_id,
                        "score": float(scores[int(idx)]),
                        "epoch": payload.get("epoch"),
                        "metadata": payload.get("metadata"),
                    }
                )
            return ranked

        strict_readpath = os.getenv("STRICT_READPATH", "false").lower() == "true"
        baseline_providers = dict(self.collection_providers)
        baseline_instances = set(self._provider_instances.keys())

        provider_instance: IndexProvider
        provider_name_used: str
        if provider:
            provider_instance = self.get_ephemeral_provider(collection, provider)
            provider_name_used = provider
        else:
            provider_instance = self._ensure_provider(collection)
            provider_name_used = self.collection_providers.get(collection, provider_instance.name)

        total_start = time.perf_counter()
        if ef_search is not None:
            try:
                ef_override = max(1, int(ef_search))
            except (TypeError, ValueError):
                ef_override = None
        else:
            ef_override = None

        if ef_override is not None:
            results = provider_instance.search(
                query,
                state.vectors,
                top_k=top_k,
                ef_search=ef_override,
            )
        else:
            results = provider_instance.search(query, state.vectors, top_k=top_k)
        total_ms = (time.perf_counter() - total_start) * 1000.0

        plan = provider_instance.get_last_plan() or {}
        params = dict(plan.get("params") or {})
        params.setdefault("metric", metric_name)
        if ef_override is not None:
            params["efSearchOverride"] = ef_override
        counters = dict(plan.get("counters") or {})
        default_vectors = len(state.vectors)
        counters.setdefault("visited", default_vectors)
        counters.setdefault("scanned", len(results))
        candidate_count = counters.get("candidate_count")
        if candidate_count is None:
            candidate_count = max(len(results), min(default_vectors, counters.get("visited", default_vectors)))
        counters["candidate_count"] = int(candidate_count)
        counters.setdefault("total_points", default_vectors)

        timings = dict(plan.get("timings_ms") or {})
        # Backwards compatibility with earlier plan structures.
        if "preprocess" not in timings:
            timings["preprocess"] = timings.pop("distance", 0.0)
        if "index_search" not in timings:
            timings["index_search"] = timings.get("search", 0.0)
        if timings.get("index_search", 0.0) == 0.0:
            timings["index_search"] = plan.get("timings_ms", {}).get("index_search", 0.0)
        if timings.get("index_search", 0.0) == 0.0 and "total" in timings and "preprocess" in timings:
            timings["index_search"] = max(0.0, timings.get("total", 0.0) - timings.get("preprocess", 0.0))
        if "postprocess" not in timings:
            timings["postprocess"] = timings.pop("rank", 0.0)
        timings.setdefault("proof", plan.get("timings_ms", {}).get("proof", 0.0))
        timings.setdefault("total", plan.get("timings_ms", {}).get("total", total_ms))

        plan_name = plan.get("plan", "ann" if provider_instance.name != "exact" else "exact")
        if counters.get("visited", default_vectors) >= default_vectors or counters.get("scanned", default_vectors) >= default_vectors:
            plan_name = "exact"

        provider_version = (
            getattr(provider_instance, "version", None)
            or getattr(provider_instance, "_version", None)
            or "1.0"
        )

        plan_payload = {
            "plan": plan_name,
            "index": plan.get("index", provider_instance.name),
            "params": params,
            "counters": counters,
            "timings_ms": timings,
            "total_vectors": default_vectors,
            "provider_used": {
                "name": provider_name_used,
                "version": str(provider_version),
            },
        }
        self._last_search_plan = plan_payload

        if provider and strict_readpath:
            if self.collection_providers != baseline_providers or set(self._provider_instances.keys()) != baseline_instances:
                logger.warning(
                    "read-only search attempted to mutate provider state; reverting",  # pragma: no cover - defensive
                )
                raise RuntimeError("read-only provider override attempted to mutate state")

        ranked = []
        for vector_id, score in results:
            payload = state.vectors[vector_id]
            ranked.append(
                {
                    "id": vector_id,
                    "score": float(score),
                    "epoch": payload.get("epoch"),
                    "metadata": payload.get("metadata"),
                }
            )
        return ranked

    def last_search_plan(self) -> Dict[str, Any]:
        return dict(self._last_search_plan)

    def build_index(self, collection: str) -> Dict[str, Any]:
        state = self.collections.get(collection)
        if state is None:
            raise KeyError(collection)

        provider = self._ensure_provider(collection)
        start = time.perf_counter()
        provider.build(state.vectors)
        duration_ms = (time.perf_counter() - start) * 1000.0

        params: Dict[str, Any] = {
            "metric": state.indexes.get("metric", "cosine"),
        }
        if hasattr(provider, "_config"):
            params.update({k: v for k, v in getattr(provider, "_config").items() if v is not None})
        params.setdefault("provider", provider.name)

        status = {
            "collection": collection,
            "ready": True,
            "points_indexed": len(state.vectors),
            "provider": provider.name,
            "params": params,
            "duration_ms": duration_ms,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "proof_version": int(state.indexes.get("proof_version", 0) or 0),
        }
        self._index_status[collection] = status
        return status

    def get_index_status(self, collection: str) -> Dict[str, Any]:
        state = self.collections.get(collection)
        points_indexed = len(state.vectors) if state else 0
        proof_version = int(state.indexes.get("proof_version", 0) or 0) if state else 0
        status = self._index_status.get(collection)
        if status:
            status = dict(status)
            status["points_indexed"] = points_indexed
            status["proof_version"] = proof_version
            return status
        provider_name = self.collection_providers.get(collection)
        return {
            "collection": collection,
            "ready": False,
            "points_indexed": points_indexed,
            "provider": provider_name,
            "params": {"provider": provider_name} if provider_name else {},
            "updated_at": None,
            "proof_version": proof_version,
        }

    def list_providers(self) -> Dict[str, Dict[str, Any]]:
        catalogue = {}
        for name, (cls, kwargs) in PROVIDERS.items():
            catalogue[name] = {
                "class": f"{cls.__module__}.{cls.__name__}",
                "default_config": kwargs,
            }
        return catalogue

    def set_collection_provider(self, collection: str, provider_name: str) -> Dict[str, Any]:
        if provider_name not in PROVIDERS:
            raise KeyError(f"unknown provider: {provider_name}")

        state = self.get_collection_state(collection)
        previous_provider = state.indexes.get("provider")
        proof_version = int(state.indexes.get("proof_version", 0)) + 1

        state.indexes["provider"] = provider_name
        state.indexes["proof_version"] = proof_version
        self.collection_providers[collection] = provider_name
        self._provider_instances.pop(collection, None)

        status = {
            "collection": collection,
            "provider": provider_name,
            "previous_provider": previous_provider,
            "proof_version": proof_version,
            "ready": False,
            "updated_at": datetime.utcnow().isoformat() + "Z",
        }
        self._index_status[collection] = status

        self._persist_collection(collection, state)
        return status

    # ------------------------------------------------------------------
    # internal helpers
    def _collection_path(self, collection: str) -> Path:
        return self.base_path / f"{collection}.json"

    def _persist_collection(self, collection: str, state: CollectionState) -> None:
        path = self._collection_path(collection)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=2, sort_keys=True)

    def _load_existing_state(self) -> None:
        for file_path in self.base_path.glob("*.json"):
            try:
                with file_path.open("r", encoding="utf-8") as fh:
                    payload = json.load(fh)
                collection = file_path.stem
                self.collections[collection] = CollectionState.from_dict(payload)
                state = self.collections[collection]
                for vector_id, vector_payload in state.vectors.items():
                    canonical_metadata = self._canonicalize_metadata(
                        dict(vector_payload.get("metadata", {})),
                        context=f"{collection}:{vector_id}",
                    )
                    vector_payload["metadata"] = canonical_metadata
                provider_name = self.collections[collection].indexes.get("provider")
                if provider_name:
                    self.collection_providers[collection] = provider_name
            except (json.JSONDecodeError, OSError):
                # Skip corrupted artefacts but keep going for other collections.
                continue

    @staticmethod
    def _ensure_record(item: Union[VectorRecord, Dict[str, Any]]) -> VectorRecord:
        if isinstance(item, VectorRecord):
            return item
        if isinstance(item, dict):
            if "id" not in item:
                raise KeyError("Vector record dictionaries must include an 'id' field.")
            return VectorRecord(
                id=item["id"],
                values=item.get("vector") or item.get("values") or [],
                metadata=item.get("metadata", {}),
                epoch=item.get("epoch"),
            )
        raise TypeError("Unsupported record type: %r" % (type(item),))

    def _ensure_provider(self, collection: str) -> IndexProvider:
        provider_name = self.collection_providers.get(collection)
        if not provider_name:
            provider_name = self.collections.get(collection, CollectionState()).indexes.get("provider")
        if not provider_name:
            provider_name = list(PROVIDERS.keys())[0]
            self.collection_providers[collection] = provider_name

        provider = self._provider_instances.get(collection)
        if provider is None:
            provider = get_provider(provider_name)
            state = self.collections.setdefault(collection, CollectionState())
            metric = state.indexes.get("metric")
            if metric and hasattr(provider, "_metric"):
                provider._metric = metric
                if hasattr(provider, "_config"):
                    provider._config["metric"] = metric
            provider.build(state.vectors)
            self._provider_instances[collection] = provider
        return provider

    def get_ephemeral_provider(self, collection: str, provider_name: str) -> IndexProvider:
        if provider_name not in PROVIDERS:
            raise KeyError(f"unknown provider: {provider_name}")

        state = self.collections.get(collection)
        if state is None:
            state = self.get_collection_state(collection)

        metric = state.indexes.get("metric")
        params = state.indexes.get("provider_params")
        proof_version = state.indexes.get("proof_version")
        params_key = json.dumps(params, sort_keys=True) if params else None
        cache_key = (collection, provider_name, metric, params_key, proof_version)

        cached = self._ephemeral_provider_cache.get(cache_key)
        if cached is not None:
            self._ephemeral_provider_cache.move_to_end(cache_key)
            return cached

        provider = get_provider(provider_name)
        if metric and hasattr(provider, "_metric"):
            provider._metric = metric
            if hasattr(provider, "_config"):
                provider._config["metric"] = metric
        provider.build(state.vectors)

        self._ephemeral_provider_cache[cache_key] = provider
        while len(self._ephemeral_provider_cache) > self._ephemeral_cache_limit:
            self._ephemeral_provider_cache.popitem(last=False)
        return provider

    @classmethod
    def _canonicalize_metadata(
        cls, metadata: Mapping[str, Any], *, context: str = ""
    ) -> Dict[str, Any]:
        """Remove volatile fields from metadata to keep persistence deterministic."""

        removed: List[str] = []

        def _strip(value: Any, prefix: str = "") -> Any:
            if isinstance(value, Mapping):
                canonical: Dict[str, Any] = {}
                for key in sorted(value.keys()):
                    lower = key.lower()
                    full_key = f"{prefix}.{key}" if prefix else key
                    if lower in cls._VOLATILE_KEY_NAMES or any(
                        lower.endswith(suffix) for suffix in cls._VOLATILE_KEY_SUFFIXES
                    ):
                        removed.append(full_key)
                        continue
                    canonical[key] = _strip(value[key], full_key)
                return canonical
            if isinstance(value, list):
                canonical_list = [_strip(item, prefix) for item in value]
                if all(isinstance(item, Mapping) for item in canonical_list):
                    canonical_list = sorted(
                        canonical_list,
                        key=lambda item: json.dumps(item, sort_keys=True),
                    )
                return canonical_list
            return value

        canonicalised = _strip(metadata)
        if removed:
            logger.debug(
                "canonicalised metadata for %s; stripped volatile keys=%s",
                context or "record",
                removed,
            )
        return canonicalised
