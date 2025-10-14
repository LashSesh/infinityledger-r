import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urljoin

import requests

QUALITY_BASE_URL = os.getenv("QUALITY_BASE_URL", "http://localhost:8080")
QUALITY_TOKEN = os.getenv("QUALITY_TOKEN", "infinity-ledger-token")
QUALITY_COLLECTION = os.getenv("QUALITY_COLLECTION", "spiral")
QUALITY_EPOCH = os.getenv("QUALITY_EPOCH", "e1")
AUTH_TOKEN_REQUIRED = os.getenv("AUTH_TOKEN_REQUIRED", "true").lower() == "true"
REQUEST_TIMEOUT = float(os.getenv("QUALITY_TIMEOUT", "15"))


def authorization_headers() -> Dict[str, str]:
    if not AUTH_TOKEN_REQUIRED or not QUALITY_TOKEN:
        return {}
    return {"Authorization": f"Bearer {QUALITY_TOKEN}"}


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    session.headers.update(authorization_headers())
    return session


def base_url() -> str:
    return QUALITY_BASE_URL.rstrip("/") + "/"


def request_raw(
    method: str,
    path: str,
    *,
    json_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> requests.Response:
    session = build_session()
    if headers:
        session.headers.update(dict(headers))
    url = urljoin(base_url(), path.lstrip("/"))
    response = session.request(method.upper(), url, json=json_body, timeout=REQUEST_TIMEOUT)
    return response


def request_json(
    method: str,
    path: str,
    *,
    json_body: Optional[Mapping[str, Any]] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    response = request_raw(method, path, json_body=json_body, headers=headers)
    response.raise_for_status()
    return response.json()


def try_request(path: str = "healthz", *, method: str = "GET") -> Optional[requests.Response]:
    session = build_session()
    url = urljoin(base_url(), path.lstrip("/"))
    try:
        response = session.request(method.upper(), url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None
    return response


def wait_for_service(retries: int = 5, delay: float = 1.0) -> bool:
    for _ in range(retries):
        response = try_request("healthz")
        if response and response.status_code < 500:
            return True
        time.sleep(delay)
    return False


def skip_unless_service_available():
    import pytest

    if not wait_for_service():
        pytest.skip("Quality base service is not reachable")


def float_vector_to_bytes(vector: Iterable[float]) -> bytes:
    import struct

    buf = bytearray()
    for value in vector:
        buf.extend(struct.pack("<f", float(value)))
    return bytes(buf)


def hash_vector(vector: Iterable[float]) -> str:
    return hashlib.sha256(float_vector_to_bytes(vector)).hexdigest()


def sort_hits(hits: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [dict(hit) for hit in hits],
        key=lambda hit: (-float(hit.get("score", 0.0)), str(hit.get("id") or hit.get("tic_id"))),
    )


def is_monotonic_decreasing(series: Iterable[float]) -> bool:
    iterator = iter(series)
    try:
        previous = next(iterator)
    except StopIteration:
        return True
    for value in iterator:
        if not (previous > value or math.isclose(previous, value)):
            return False
        previous = value
    return True


def approx_equal(a: float, b: float, *, abs_tol: float = 1e-8, rel_tol: float = 1e-6) -> bool:
    return math.isclose(a, b, abs_tol=abs_tol, rel_tol=rel_tol)


def _golden_directories(create: bool = False) -> List[Path]:
    tests_dir = Path(__file__).resolve().parent
    project_root = tests_dir.parent
    candidates = [
        project_root / "assets" / "golden",
        tests_dir / "assets" / "golden",
    ]
    directories: List[Path] = []
    for candidate in candidates:
        if create:
            candidate.mkdir(parents=True, exist_ok=True)
        if candidate.exists():
            directories.append(candidate)
    if not directories and create:
        default_path = candidates[0]
        default_path.mkdir(parents=True, exist_ok=True)
        directories.append(default_path)
    return directories


def golden_directory(create: bool = False) -> Path:
    directories = _golden_directories(create=create)
    if directories:
        return directories[0]
    raise FileNotFoundError("Golden asset directory is missing")


def load_golden_dataset() -> List[Dict[str, Any]]:
    dataset_path = golden_directory().joinpath("dataset.jsonl")
    rows: List[Dict[str, Any]] = []
    with open(dataset_path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_golden_expected() -> Dict[str, Any]:
    golden_path = golden_directory().joinpath("golden_expected.json")
    if not golden_path.exists():
        raise FileNotFoundError(str(golden_path))
    with open(golden_path, "r", encoding="utf-8") as handle:
        return json.load(handle)
