"""Recompute pipeline proof hashes from search responses."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def recompute_pipeline_proof(
    *,
    collection: str,
    query_vector: Sequence[float],
    top_k: int,
    provider: Optional[str],
    commit_root: str,
    result_id: str,
) -> str:
    payload = {
        "collection": collection,
        "query": list(query_vector),
        "top_k": int(top_k),
        "provider": provider,
        "commit_root": commit_root,
        "result_id": result_id,
    }
    return _hash(payload)


def _resolve_provider(payload: Mapping[str, Any], entry: Mapping[str, Any]) -> Optional[str]:
    proof_context = payload.get("proof_context")
    provider = None
    if isinstance(proof_context, Mapping):
        provider = proof_context.get("provider") or provider

    provider_used = payload.get("provider_used")
    if isinstance(provider_used, Mapping):
        provider = provider or provider_used.get("name")
    elif isinstance(provider_used, str):
        provider = provider or provider_used.split("@", 1)[0]

    headers = payload.get("headers")
    if isinstance(headers, Mapping):
        header_provider = headers.get("X-Provider-Used")
        if header_provider and not provider:
            provider = header_provider.split("@", 1)[0]

    request_provider = None
    request_payload = payload.get("request")
    if isinstance(request_payload, Mapping):
        request_provider = request_payload.get("provider")
    if provider is None and request_provider:
        provider = request_provider

    entry_provider = entry.get("provider")
    if provider is None and entry_provider:
        provider = entry_provider

    return provider


def recompute_from_search_payload(payload: Mapping[str, Any]) -> Dict[str, str]:
    commit = payload.get("commit", {})
    commit_root = str(commit.get("commit_root"))
    results: Dict[str, str] = {}
    request_payload = payload.get("request") if isinstance(payload.get("request"), Mapping) else {}
    for entry in payload.get("results", []):
        if not isinstance(entry, Mapping):
            continue
        collection = (
            payload.get("collection")
            or entry.get("collection")
            or (request_payload.get("collection") if isinstance(request_payload, Mapping) else None)
        )
        if not collection:
            raise ValueError("Collection is required to recompute pipeline proof")
        query_vector = (
            entry.get("query_vector")
            or payload.get("query_vector")
            or request_payload.get("query_vector")
        )
        if query_vector is None:
            raise ValueError("Query vector must be present in payload or entry")
        top_k = (
            payload.get("top_k")
            or request_payload.get("top_k")
            or len(payload.get("results", []))
            or 5
        )
        provider_name = _resolve_provider(payload, entry)
        if (
            isinstance(request_payload, Mapping)
            and request_payload.get("provider")
            and provider_name
            and provider_name != request_payload.get("provider")
        ):
            print(
                "[recompute_pipeline] provider override detected: "
                f"resolved={provider_name} requested={request_payload.get('provider')}",
                file=sys.stderr,
            )
        result_id = entry.get("id") or entry.get("tic_id")
        if result_id is None:
            continue
        results[result_id] = recompute_pipeline_proof(
            collection=collection,
            query_vector=query_vector,
            top_k=int(top_k),
            provider=provider_name,
            commit_root=commit_root,
            result_id=str(result_id),
        )
    return results


def load_json(path: Path) -> Mapping[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("Search payload must be a JSON object")
    return data


def run_cli(search_path: Path) -> int:
    payload = load_json(search_path)
    results = recompute_from_search_payload(payload)
    print(json.dumps(results, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute pipeline proof hashes")
    parser.add_argument("--search", type=Path, required=True, help="Search response JSON")
    args = parser.parse_args(argv)
    return run_cli(args.search)


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
