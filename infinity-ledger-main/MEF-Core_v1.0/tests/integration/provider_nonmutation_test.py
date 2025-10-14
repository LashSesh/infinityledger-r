"""Integration tests ensuring provider overrides are read-only."""

from __future__ import annotations

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


@pytest.mark.integration
def test_provider_override_is_ephemeral() -> None:
    skip_unless_service_available()

    roundtrip = _roundtrip_sample()
    if roundtrip is None:
        pytest.skip("No dataset entries produced a valid PoR for provider override checks")

    body = {
        "collection": roundtrip.collection,
        "query_vector": roundtrip.vector,
        "top_k": len(roundtrip.hits) or 5,
        "mode": "ann",
        "membership_proof": False,
        "pipeline_proof": False,
    }

    baseline_response = request_raw("POST", "/search", json_body=body)
    baseline_response.raise_for_status()
    plan_default = request_json("GET", "/debug/search-plan")
    provider_default = (
        plan_default.get("provider_used", {}).get("name")
        if isinstance(plan_default, dict)
        else None
    )
    assert provider_default, "default provider not reported"
    header_default = baseline_response.headers.get("X-Provider-Used")
    assert header_default and header_default.startswith(provider_default)

    baseline_payload = baseline_response.json()
    baseline_hits = sort_hits(baseline_payload.get("results", []))
    baseline_commit = baseline_payload.get("commit", {}).get("commit_root")
    assert baseline_payload.get("provider_used"), "baseline search missing provider_used"
    assert (
        baseline_payload.get("proof_context", {}).get("provider")
        == plan_default.get("provider_used", {}).get("name")
    )

    override_body = dict(body)
    override_body["provider"] = ALT_PROVIDER
    override_response = request_raw("POST", "/search", json_body=override_body)
    override_response.raise_for_status()
    plan_override = request_json("GET", "/debug/search-plan")
    assert plan_override.get("provider_used", {}).get("name") == ALT_PROVIDER
    header_override = override_response.headers.get("X-Provider-Used")
    assert header_override and header_override.startswith(ALT_PROVIDER)
    override_payload = override_response.json()
    assert override_payload.get("provider_used") and override_payload.get("provider_used").startswith(ALT_PROVIDER)
    assert override_payload.get("proof_context", {}).get("provider") == ALT_PROVIDER

    repeat_response = request_raw("POST", "/search", json_body=body)
    repeat_response.raise_for_status()
    repeat_payload = repeat_response.json()
    repeat_hits = sort_hits(repeat_payload.get("results", []))
    assert repeat_hits == baseline_hits
    assert repeat_payload.get("commit", {}).get("commit_root") == baseline_commit
    assert repeat_payload.get("provider_used") == baseline_payload.get("provider_used")

    plan_repeat = request_json("GET", "/debug/search-plan")
    repeat_provider = plan_repeat.get("provider_used", {}).get("name")
    assert repeat_provider == provider_default

    status_payload = request_json(
        "GET",
        f"/index/status?collection={roundtrip.collection}",
    )
    assert status_payload.get("provider") == provider_default
    assert status_payload.get("ready") in {True, False}
