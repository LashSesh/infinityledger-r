"""Pull Prometheus metrics from the running API and persist to JSON."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, Mapping

QUALITY_BASE_URL = os.environ.get("QUALITY_BASE_URL", "http://localhost:8080")
QUALITY_TOKEN = os.environ.get("QUALITY_TOKEN", "")


def _parse_prometheus(text: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        key, value = parts
        try:
            metrics[key] = float(value)
        except ValueError:
            continue
    return metrics


def fetch_metrics(path: str = "/metrics", timeout: float = 10.0) -> Dict[str, float]:
    url = f"{QUALITY_BASE_URL.rstrip('/')}{path}"
    headers: Dict[str, str] = {}
    if QUALITY_TOKEN:
        headers["Authorization"] = f"Bearer {QUALITY_TOKEN}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
            text = response.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError(f"Failed to fetch metrics from {url}: {exc}") from exc

    return _parse_prometheus(text)


def dump_metrics(path: Path, metrics: Mapping[str, float]) -> None:
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "metrics": dict(metrics),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    try:
        metrics = fetch_metrics()
    except RuntimeError as exc:
        print(json.dumps({"written": False, "error": str(exc)}), file=sys.stderr)
        return 1

    dump_metrics(Path("assets/bench/metrics.json"), metrics)
    print(json.dumps({"written": True, "keys": sorted(metrics.keys())}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
