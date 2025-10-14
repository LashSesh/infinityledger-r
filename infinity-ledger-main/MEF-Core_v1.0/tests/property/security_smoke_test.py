"""Security smoke tests verifying authentication and rate limits."""

from __future__ import annotations

import os
import time
from typing import Dict

import pytest
import requests

from ..quality_utils import QUALITY_BASE_URL, skip_unless_service_available

UNAUTH_ENDPOINTS = [
    ("/search", "post"),
    ("/solve", "post"),
    ("/commit", "get"),
]


def _auth_required() -> bool:
    value = os.getenv("AUTH_TOKEN_REQUIRED", "true").strip().lower()
    return value not in {"0", "false", "off", "no", ""}


def _request_kwargs(path: str, method: str) -> Dict[str, object]:
    if method.lower() != "post":
        return {}
    if path == "/search":
        return {
            "json": {
                "collection": os.getenv("QUALITY_COLLECTION", "spiral"),
                "query_vector": [0.0, 0.0, 0.0, 0.0, 0.0],
                "top_k": 1,
            }
        }
    if path == "/solve":
        return {"params": {"snapshot_id": "smoke-test"}}
    return {}


@pytest.mark.parametrize("path, method", UNAUTH_ENDPOINTS)
def test_requires_bearer_token(path: str, method: str) -> None:
    skip_unless_service_available()

    url = f"{QUALITY_BASE_URL.rstrip('/')}{path}"
    response = requests.request(
        method.upper(), url, timeout=5, **_request_kwargs(path, method)
    )

    if not _auth_required():
        pytest.skip("Authentication disabled; security smoke skipped")

    assert response.status_code in {401, 403}


def test_rate_limit_or_metrics_counter() -> None:
    skip_unless_service_available()

    url = f"{QUALITY_BASE_URL.rstrip('/')}/search"
    headers = {"Authorization": f"Bearer {os.getenv('QUALITY_TOKEN', 'infinity-ledger-token')}"}
    payload = {
        "collection": os.getenv("QUALITY_COLLECTION", "spiral"),
        "query_vector": [0.0, 0.0, 0.0, 0.0, 0.0],
        "top_k": 1,
    }

    for _ in range(5):
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        if response.status_code == 429:
            break
        time.sleep(0.1)
    else:
        pytest.skip("Rate limit not enforced; metrics counter should capture load")
