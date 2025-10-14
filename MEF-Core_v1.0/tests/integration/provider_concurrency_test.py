"""Concurrency tests ensuring provider overrides remain isolated."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

import pytest

from ..property.pipeline_helpers import SolveHoldDueToPOR, run_roundtrip
from ..quality_utils import (
    load_golden_dataset,
    request_json,
    request_raw,
    skip_unless_service_available,
    sort_hits,
)

ALT_PROVIDER = "ivf_pq"


def _roundtrip_sample() -> Optional[Dict[str, object]]:
    dataset = load_golden_dataset()
    for sample in dataset:
        try:
            return run_roundtrip(sample, membership_proof=False, pipeline_proof=False)
        except SolveHoldDueToPOR:
            continue
    return None


def _search(body: Dict[str, object]) -> Dict[str, object]:
    response = request_raw("POST", "/search", json_body=body)
    response.raise_for_status()
    payload = response.json()
    return {
        "hits": sort_hits(payload.get("results", [])),
        "commit": payload.get("commit", {}).get("commit_root"),
        "header": response.headers.get("X-Provider-Used"),
    }


@pytest.mark.integration
def test_concurrent_provider_overrides_do_not_leak() -> None:
    skip_unless_service_available()

    roundtrip = _roundtrip_sample()
    if roundtrip is None:
        pytest.skip("No dataset entries produced a valid PoR for provider concurrency checks")

    body: Dict[str, object] = {
        "collection": roundtrip.collection,
        "query_vector": roundtrip.vector,
        "top_k": len(roundtrip.hits) or 5,
        "mode": "ann",
        "membership_proof": False,
        "pipeline_proof": False,
    }

    baseline = _search(body)
    assert baseline["header"] is not None

    override_body = dict(body)
    override_body["provider"] = ALT_PROVIDER

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_default = executor.submit(_search, dict(body))
        future_override = executor.submit(_search, override_body)
        concurrent_default = future_default.result()
        concurrent_override = future_override.result()

    assert concurrent_override["header"] and concurrent_override["header"].startswith(ALT_PROVIDER)
    assert concurrent_default["header"] and concurrent_default["header"].startswith(baseline["header"].split("@")[0])
    assert concurrent_default["hits"] == baseline["hits"]
    assert concurrent_default["commit"] == baseline["commit"]

    repeat = _search(body)
    assert repeat["hits"] == baseline["hits"]
    assert repeat["commit"] == baseline["commit"]
    assert repeat["header"] and repeat["header"].startswith(baseline["header"].split("@")[0])

    status_payload = request_json(
        "GET",
        f"/index/status?collection={roundtrip.collection}",
    )
    assert status_payload.get("provider") == baseline["header"].split("@")[0]
