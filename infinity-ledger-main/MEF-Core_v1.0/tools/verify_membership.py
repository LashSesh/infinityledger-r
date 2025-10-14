"""Offline membership-proof verification utilities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from vector_db.proof_registry import MembershipProof


def _normalise_siblings(raw: Iterable[Any]) -> List[Tuple[str, str]]:
    siblings: List[Tuple[str, str]] = []
    for item in raw:
        position: Optional[str]
        hash_value: Optional[str]
        if isinstance(item, Mapping):
            position = str(item.get("position") or item.get("dir") or item.get("direction") or "")
            hash_value = str(item.get("hash") or item.get("value") or item.get("sibling") or "")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            position = str(item[0])
            hash_value = str(item[1])
        else:
            raise ValueError(f"Unsupported sibling representation: {item!r}")

        position = position.lower()
        if position not in {"left", "right"}:
            raise ValueError(f"Invalid sibling direction: {position}")
        siblings.append((position, hash_value))
    return siblings


def verify_membership_hit(
    hit: Mapping[str, Any],
    commit_root: str,
    *,
    allow_missing: bool = False,
    root_override: Optional[str] = None,
) -> bool:
    proof_payload = hit.get("membership_proof")
    if not proof_payload:
        return bool(allow_missing)

    siblings = _normalise_siblings(proof_payload.get("siblings", []))
    preferred_root = root_override
    if not preferred_root:
        preferred_root = str(hit.get("root") or "").strip() or None
    if not preferred_root and isinstance(proof_payload, Mapping):
        preferred_root = (
            str(proof_payload.get("commit_root") or proof_payload.get("root") or "").strip()
            or None
        )
    effective_root = preferred_root or commit_root
    if not effective_root:
        return False
    proof = MembershipProof(
        collection=str(proof_payload.get("collection")),
        vector_id=str(proof_payload.get("vector_id") or hit.get("id")),
        leaf=str(proof_payload.get("leaf")),
        siblings=siblings,
        collection_root=str(proof_payload.get("collection_root")),
        commit_root=str(effective_root),
    )
    return proof.verify(leaf_hash=proof.leaf, commit_root=str(effective_root))


def verify_hits(
    commit: Mapping[str, Any],
    hits: Sequence[Mapping[str, Any]],
    *,
    allow_missing: bool = False,
    root_override: Optional[str] = None,
) -> Dict[str, bool]:
    commit_root = str(commit.get("commit_root") or "")
    results: Dict[str, bool] = {}
    for hit in hits:
        vector_id = str(hit.get("id") or hit.get("tic_id"))
        results[vector_id] = verify_membership_hit(
            hit,
            commit_root,
            allow_missing=allow_missing,
            root_override=root_override,
        )
    return results


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_hits(path: Path) -> List[MutableMapping[str, Any]]:
    payload = _load_json(path)
    if isinstance(payload, Mapping) and "results" in payload:
        return list(payload["results"])
    if isinstance(payload, Sequence):
        return list(payload)
    raise ValueError("Unsupported hits payload")


def _load_commit(path: Path) -> Mapping[str, Any]:
    payload = _load_json(path)
    if isinstance(payload, Mapping):
        return payload
    raise ValueError("Commit payload must be a JSON object")


def run_cli(
    commit_path: Path,
    hits_path: Path,
    *,
    allow_missing: bool = False,
    root_override: Optional[str] = None,
) -> int:
    commit = _load_commit(commit_path)
    hits = _load_hits(hits_path)
    results = verify_hits(
        commit,
        hits,
        allow_missing=allow_missing,
        root_override=root_override,
    )
    failed = [vector_id for vector_id, ok in results.items() if not ok]
    if failed:
        print(json.dumps({"verified": False, "failed": failed}, indent=2))
        return 1
    print(json.dumps({"verified": True, "checked": list(results.keys())}, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify membership proofs against a commit root")
    parser.add_argument("--commit", type=Path, required=True, help="Path to commit JSON")
    parser.add_argument("--hits", type=Path, required=True, help="Path to hits JSON")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Treat missing membership proofs as success",
    )
    parser.add_argument(
        "--root",
        type=str,
        help="Override commit root used for verification (optional)",
    )
    args = parser.parse_args(argv)
    return run_cli(
        args.commit,
        args.hits,
        allow_missing=args.allow_missing,
        root_override=args.root,
    )


if __name__ == "__main__":  # pragma: no cover - manual invocation
    raise SystemExit(main())
