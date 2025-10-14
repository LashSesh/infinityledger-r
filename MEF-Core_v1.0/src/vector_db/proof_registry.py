"""Deterministic membership proof construction for vector collections.

The :mod:`vector_db.index_manager` keeps vectors on disk but does not expose a
cryptographic view over the stored payloads.  For proof-carrying retrieval we
derive a Sparse-Merkle like commitment where each leaf corresponds to a single
vector entry.  Proofs are generated lazily and cached together with a global
commit root so callers can validate lookups against a signed digest that is
stable for a given collection state.

The implementation purposely keeps the construction lightweight; it uses
standard SHA-256 hashing and stable JSON serialisation to guarantee
deterministic outputs across platforms which is sufficient for the regression
tests that validate proofs against the published commit root.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from .index_manager import CollectionState


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_json(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


_VOLATILE_KEYS = {
    "timestamp",
    "created",
    "created_at",
    "updated",
    "updated_at",
    "ingested",
    "ingested_at",
    "acquired",
    "activated",
    "generated",
    "refreshed",
}
_VOLATILE_SUFFIXES = ("_at", "_time", "_timestamp")


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _normalise_key_fragment(fragment: str) -> str:
    """Normalise a metadata fragment for suffix checks.

    We avoid splitting sequences that are already upper snake-case so keys like
    ``EVENT_TIMESTAMP`` stay intact while camelCase/PascalCase variants gain
    predictable underscores for suffix detection.
    """

    cleaned = fragment.replace("-", "_")
    if not cleaned:
        return ""
    if cleaned.isupper():
        return cleaned.lower()
    normalised = _CAMEL_BOUNDARY.sub("_", cleaned).lower()
    return normalised


def _is_volatile(key: str) -> bool:
    lk = key.lower()
    if (lk in _VOLATILE_KEYS) or lk.endswith(_VOLATILE_SUFFIXES) or lk.endswith("_ts"):
        return True

    fragments = [fragment for fragment in lk.split("_") if fragment]
    if fragments and fragments[-1] in _VOLATILE_KEYS:
        return True

    return False


def _is_volatile_key(key: str) -> bool:
    last_fragment = key.rsplit(".", 1)[-1]
    normalised = _normalise_key_fragment(last_fragment)
    if not normalised:
        return False
    return _is_volatile(normalised)


def _canonicalise_vector(vector: Optional[object]) -> List[float]:
    if isinstance(vector, list):
        return [float(value) for value in vector]
    if isinstance(vector, tuple):
        return [float(value) for value in vector]
    return []


def _canonicalise_metadata(metadata: Optional[object]) -> Dict[str, Any]:
    removed: List[str] = []

    def _strip(value: Any, prefix: str = "") -> Any:
        if isinstance(value, Mapping):
            canonical: Dict[str, Any] = {}
            for key in sorted(value.keys()):
                full_key = f"{prefix}.{key}" if prefix else key
                if _is_volatile_key(full_key):
                    removed.append(full_key)
                    continue
                canonical[key] = _strip(value[key], full_key)
            return canonical
        if isinstance(value, list):
            canonical_list = [_strip(item, prefix) for item in value]
            if all(isinstance(item, Mapping) for item in canonical_list):
                canonical_list = sorted(
                    canonical_list, key=lambda item: json.dumps(item, sort_keys=True)
                )
            return canonical_list
        return value

    if isinstance(metadata, Mapping):
        canonicalised = _strip(metadata)
    else:
        canonicalised = {}

    if removed:
        logging.getLogger(__name__).debug(
            "proof registry stripped volatile metadata keys=%s", removed
        )

    return canonicalised


def _leaf_hash(vector_id: str, payload: Mapping[str, object]) -> str:
    material = {
        "id": vector_id,
        "epoch": payload.get("epoch"),
        "vector": _canonicalise_vector(payload.get("vector")),
        "metadata": _canonicalise_metadata(payload.get("metadata")),
    }
    return _sha256(_stable_json(material))


def _combine_hash(left: str, right: str) -> str:
    return _sha256(f"{left}|{right}".encode("utf-8"))


@dataclass
class MembershipProof:
    """Sparse Merkle style proof for a single vector entry."""

    collection: str
    vector_id: str
    leaf: str
    siblings: List[Tuple[str, str]]  # (position, hash)
    collection_root: str
    commit_root: str

    def verify(self, leaf_hash: Optional[str] = None, commit_root: Optional[str] = None) -> bool:
        """Verify the proof against an optional externally supplied leaf/root."""

        running = leaf_hash or self.leaf
        for position, sibling_hash in self.siblings:
            if position == "left":
                running = _combine_hash(sibling_hash, running)
            elif position == "right":
                running = _combine_hash(running, sibling_hash)
            else:  # pragma: no cover - defensive, proofs are constructed internally
                raise ValueError(f"invalid sibling position: {position}")

        if running != self.collection_root:
            return False

        expected_root = commit_root or self.commit_root
        return expected_root == self.commit_root


class ProofRegistry:
    """Construct and cache membership proofs for vector collections."""

    def __init__(
        self,
        *,
        kid: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> None:
        self._kid = kid or os.getenv("MEF_COMMIT_KID", "ledger-root")
        self._secret = (secret or os.getenv("MEF_COMMIT_SECRET") or "MEF-SEED-COMMIT").encode("utf-8")
        self._lock = threading.Lock()
        self._collection_roots: Dict[str, str] = {}
        self._collection_versions: Dict[str, int] = {}
        self._proofs: Dict[Tuple[str, str], MembershipProof] = {}
        self._commit_root: str = "0" * 64
        self._signature: str = self._sign_commit(self._commit_root)
        self._logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    @property
    def kid(self) -> str:
        return self._kid

    @property
    def commit_root(self) -> str:
        return self._commit_root

    @property
    def signature(self) -> str:
        return self._signature

    # ------------------------------------------------------------------
    def refresh_from_collections(self, collections: Mapping[str, CollectionState]) -> None:
        """Recompute the commit root from the provided collection state."""

        with self._lock:
            previous_root = self._commit_root
            updated_roots: Dict[str, str] = dict(self._collection_roots)
            updated_proofs: Dict[Tuple[str, str], MembershipProof] = dict(self._proofs)
            changed = False

            active_collections = set(collections.keys())

            for collection in list(updated_roots.keys()):
                if collection not in active_collections:
                    changed = True
                    updated_roots.pop(collection, None)
                    self._collection_versions.pop(collection, None)
                    updated_proofs = {
                        key: value for key, value in updated_proofs.items() if key[0] != collection
                    }

            for collection, state in collections.items():
                version = int(state.indexes.get("proof_version", 0))
                previous_version = self._collection_versions.get(collection)

                if (
                    previous_version is None
                    or previous_version != version
                    or collection not in updated_roots
                ):
                    root, proofs = self._build_collection_root(collection, state.vectors)
                    updated_roots[collection] = root
                    updated_proofs = {
                        key: value for key, value in updated_proofs.items() if key[0] != collection
                    }
                    updated_proofs.update(proofs)
                    self._collection_versions[collection] = version
                    changed = True

            if changed or not self._collection_roots:
                self._collection_roots = updated_roots
                self._proofs = updated_proofs
                combined_root = self._combine_collection_roots(updated_roots)
                self._commit_root = combined_root
                self._signature = self._sign_commit(combined_root)
                if combined_root != previous_root:
                    details = {
                        "previous": previous_root,
                        "current": combined_root,
                        "collections": {
                            name: {
                                "vectors": len(collections[name].vectors),
                                "root": updated_roots.get(name),
                                "version": self._collection_versions.get(name, 0),
                            }
                            for name in sorted(updated_roots)
                        },
                    }
                    self._logger.debug(
                        "commit root updated: %s", json.dumps(details, sort_keys=True)
                    )

    def get_membership_proof(self, collection: str, vector_id: str) -> Optional[MembershipProof]:
        with self._lock:
            return self._proofs.get((collection, vector_id))

    def get_collection_root(self, collection: str) -> Optional[str]:
        with self._lock:
            return self._collection_roots.get(collection)

    def get_commit_snapshot(self) -> Dict[str, str]:
        with self._lock:
            return {
                "commit_root": self._commit_root,
                "kid": self._kid,
                "signature": self._signature,
            }

    def batch_membership_proofs(self, members: Iterable[Tuple[str, str]]) -> List[MembershipProof]:
        proofs: List[MembershipProof] = []
        with self._lock:
            for collection, vector_id in members:
                proof = self._proofs.get((collection, vector_id))
                if proof:
                    proofs.append(proof)
        return proofs

    def rotate_secret(self, *, kid: Optional[str] = None, secret: Optional[str] = None) -> Dict[str, str]:
        with self._lock:
            if kid:
                self._kid = kid
            if secret:
                self._secret = secret.encode("utf-8")
            self._signature = self._sign_commit(self._commit_root)
            return {
                "commit_root": self._commit_root,
                "kid": self._kid,
                "signature": self._signature,
            }

    # ------------------------------------------------------------------
    def _build_collection_root(
        self,
        collection: str,
        vectors: MutableMapping[str, Mapping[str, object]],
    ) -> Tuple[str, Dict[Tuple[str, str], MembershipProof]]:
        vector_items = sorted(vectors.items(), key=lambda item: item[0])
        if not vector_items:
            empty_root = _sha256(f"{collection}|empty".encode("utf-8"))
            return empty_root, {}

        leaves = [(vector_id, _leaf_hash(vector_id, payload)) for vector_id, payload in vector_items]
        level = [leaf_hash for _, leaf_hash in leaves]
        tree_levels: List[List[str]] = [level]

        while len(level) > 1:
            next_level: List[str] = []
            for idx in range(0, len(level), 2):
                left = level[idx]
                right = level[idx + 1] if idx + 1 < len(level) else left
                combined = _combine_hash(left, right)
                next_level.append(combined)
            level = next_level
            tree_levels.append(level)

        root_hash = level[0]

        proofs: Dict[Tuple[str, str], MembershipProof] = {}
        for position, (vector_id, leaf_hash) in enumerate(leaves):
            siblings: List[Tuple[str, str]] = []
            index = position
            for level_values in tree_levels[:-1]:
                if index % 2 == 0:
                    sibling_index = index + 1 if index + 1 < len(level_values) else index
                    sibling_hash = level_values[sibling_index]
                    siblings.append(("right", sibling_hash))
                else:
                    sibling_hash = level_values[index - 1]
                    siblings.append(("left", sibling_hash))
                index //= 2

            proofs[(collection, vector_id)] = MembershipProof(
                collection=collection,
                vector_id=vector_id,
                leaf=leaf_hash,
                siblings=siblings,
                collection_root=root_hash,
                commit_root="",  # filled after commit aggregation
            )

        return root_hash, proofs

    def _combine_collection_roots(self, roots: Mapping[str, str]) -> str:
        if not roots:
            return _sha256(b"empty-commit")

        digest = ""
        for name in sorted(roots):
            digest = _sha256(f"{digest}|{name}|{roots[name]}".encode("utf-8"))

        # Populate commit root on all cached proofs.
        for key, proof in self._proofs.items():
            self._proofs[key] = MembershipProof(
                collection=proof.collection,
                vector_id=proof.vector_id,
                leaf=proof.leaf,
                siblings=proof.siblings,
                collection_root=proof.collection_root,
                commit_root=digest,
            )

        return digest

    def _sign_commit(self, commit_root: str) -> str:
        signature = hmac.new(self._secret, commit_root.encode("utf-8"), hashlib.sha256)
        return signature.hexdigest()


__all__ = ["MembershipProof", "ProofRegistry"]

