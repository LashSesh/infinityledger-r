"""API contract smoke test using OpenAPI specification."""

from __future__ import annotations

from ..quality_utils import request_json, skip_unless_service_available

REQUIRED_PATHS = [
    "/healthz",
    "/readyz",
    "/acquisition",
    "/search",
    "/solve",
    "/tic/{id}",
    "/tic/query",
    "/commit",
    "/proof/{id}",
    "/gate/fsm",
    "/mode",
]


def test_openapi_contract_contains_required_paths() -> None:
    skip_unless_service_available()

    openapi = request_json("GET", "/openapi.json")
    assert "paths" in openapi
    paths = set(openapi["paths"].keys())
    for required in REQUIRED_PATHS:
        assert required in paths, f"Missing path {required}"
