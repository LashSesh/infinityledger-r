"""Ensure the compare runner always emits reports with status metadata."""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bench.drivers.base import DriverUnavailable, VectorStoreDriver


def _load_compare_module():
    """Load the compare.py module directly, bypassing the package __init__.py."""
    compare_py_path = Path(__file__).parent / "compare.py"
    spec = importlib.util.spec_from_file_location("_test_compare_module", compare_py_path)
    if not (spec and spec.loader):
        raise ImportError(f"Could not load compare.py from {compare_py_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _HappyDriver(VectorStoreDriver):
    def __init__(self, name: str, metric: str = "cosine") -> None:
        super().__init__(metric)
        self.name = name

    def connect(self) -> None:  # pragma: no cover - trivial
        return None

    def clear(self, namespace: str) -> None:  # pragma: no cover - trivial
        return None

    def upsert(self, items, namespace: str, batch_size: int = 1000) -> None:  # pragma: no cover
        return None

    def search(self, query, k: int, namespace: str):  # pragma: no cover - deterministic sample
        return [(f"{self.name}-hit", 0.99)]


class _MissingDriver(VectorStoreDriver):
    name = "Qdrant"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)

    def connect(self) -> None:  # pragma: no cover - invoked via runner
        raise DriverUnavailable(self.name, "QDRANT_URL not configured")

    def clear(self, namespace: str) -> None:  # pragma: no cover - unused in test
        raise AssertionError("clear() should not be called")

    def upsert(self, items, namespace: str, batch_size: int = 1000) -> None:  # pragma: no cover
        raise AssertionError("upsert() should not be called")

    def search(self, query, k: int, namespace: str):  # pragma: no cover - unused in test
        raise AssertionError("search() should not be called")


class _ExitDriver(VectorStoreDriver):
    name = "ExitTarget"

    def __init__(self, metric: str = "cosine") -> None:
        super().__init__(metric)

    def connect(self) -> None:  # pragma: no cover - invoked via runner
        raise SystemExit("synthetic exit")

    def clear(self, namespace: str) -> None:  # pragma: no cover - unused in test
        raise AssertionError("clear() should not be called")

    def upsert(self, items, namespace: str, batch_size: int = 1000) -> None:  # pragma: no cover
        raise AssertionError("upsert() should not be called")

    def search(self, query, k: int, namespace: str):  # pragma: no cover - unused in test
        raise AssertionError("search() should not be called")


def test_compare_runner_emits_skipped_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "1")

    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "deadbeef")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 0

    json_payload = json.loads(module.JSON_REPORT.read_text())
    targets = {entry["name"]: entry for entry in json_payload["targets"]}

    assert targets["MEF"]["status"] == "ok"
    assert targets["FAISS"]["status"] == "ok"
    assert targets["Qdrant"]["status"] == "skipped"
    assert targets["Qdrant"]["reason"].lower().startswith("qdrant_url")
    assert targets["Qdrant"].get("token") == "qdrant"
    assert "errors" not in json_payload

    markdown = module.MARKDOWN_REPORT.read_text()
    assert "| Qdrant | skipped |" in markdown
    assert "| MEF | ok |" in markdown


def test_compare_runner_defaults_to_enabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.delenv("BENCH_COMPARE", raising=False)


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "cafebabe")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 0

    json_payload = json.loads(module.JSON_REPORT.read_text())
    targets = {entry["name"]: entry for entry in json_payload["targets"]}

    assert targets["MEF"]["status"] == "ok"
    assert targets["FAISS"]["status"] == "ok"
    assert targets["Qdrant"]["status"] == "skipped"
    assert targets["Qdrant"]["reason"].lower().startswith("qdrant_url")
    assert targets["MEF"].get("token") == "mef"
    assert "errors" not in json_payload

    markdown = module.MARKDOWN_REPORT.read_text()
    assert "| Qdrant | skipped |" in markdown
    assert "qdrant_url not configured" in markdown.lower()


def test_compare_runner_treats_auto_flag_as_enabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "auto")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "facefeed")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 0

    json_payload = json.loads(module.JSON_REPORT.read_text())
    targets = {entry["name"]: entry for entry in json_payload["targets"]}

    assert targets["MEF"]["status"] == "ok"
    assert targets["FAISS"]["status"] == "ok"
    assert targets["Qdrant"]["status"] == "skipped"
    assert "compare disabled" not in targets["Qdrant"].get("reason", "").lower()
    assert "errors" not in json_payload

    markdown = module.MARKDOWN_REPORT.read_text()
    assert "| Qdrant | skipped |" in markdown
    assert "compare disabled" not in markdown.lower()


def test_compare_runner_respects_explicit_disable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "0")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "feedbeef")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 0

    json_payload = json.loads(module.JSON_REPORT.read_text())
    targets = {entry["name"]: entry for entry in json_payload["targets"]}

    assert targets["MEF"]["status"] == "ok"
    assert targets["FAISS"]["status"] == "ok"
    assert targets["Qdrant"]["status"] == "skipped"
    assert "compare disabled" in targets["Qdrant"].get("reason", "").lower()
    assert "errors" not in json_payload


def test_compare_runner_writes_failure_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "auto")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_load_git_commit", lambda: "failurecase")

    def explode():
        raise RuntimeError("synthetic failure for coverage")

    monkeypatch.setattr(module, "_build_dataset", explode)

    exit_code = module.main()
    assert exit_code == 1

    json_payload = json.loads(module.JSON_REPORT.read_text())
    assert "error" in json_payload
    assert "synthetic failure" in json_payload["error"]
    for entry in json_payload["targets"]:
        assert entry["skipped"] is True
        assert "synthetic failure" in entry.get("reason", "").lower()

    markdown_lower = module.MARKDOWN_REPORT.read_text().lower()
    assert "compare benchmark failed" in markdown_lower
    assert "synthetic failure" in markdown_lower

    markdown = module.MARKDOWN_REPORT.read_text()
    assert "| Qdrant | skipped |" in markdown


def test_compare_runner_handles_system_exit_driver(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "1")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "deadexit")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _ExitDriver,
    }

    exit_code = module.main()
    assert exit_code == 0

    json_payload = json.loads(module.JSON_REPORT.read_text())
    targets = {entry["name"]: entry for entry in json_payload["targets"]}

    assert targets["MEF"]["status"] == "ok"
    assert targets["FAISS"]["status"] == "ok"
    assert targets["ExitTarget"]["status"] == "skipped"
    assert "synthetic exit" in targets["ExitTarget"].get("reason", "")


def test_compare_runner_requires_two_targets_when_forced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "1")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "deadbeef")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 2

    json_payload = json.loads(module.JSON_REPORT.read_text())
    assert json_payload.get("errors")
    assert "at least two" in " ".join(json_payload["errors"]).lower()


def test_compare_runner_enforces_required_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "1")
    monkeypatch.setenv("REQUIRED_TARGETS", "mef,qdrant")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_build_dataset", lambda: ([ ("id-1", [0.1, 0.2, 0.3], {"index": 0}) ], 3))
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "required")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _HappyDriver("MEF", metric),
        "faiss": lambda metric="cosine": _HappyDriver("FAISS", metric),
        "qdrant": _MissingDriver,
    }

    exit_code = module.main()
    assert exit_code == 2

    json_payload = json.loads(module.JSON_REPORT.read_text())
    assert json_payload.get("errors")
    assert any("required compare targets" in message for message in json_payload["errors"])


def test_compare_runner_writes_failure_reports_for_system_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BENCH_TARGETS", "mef,faiss,qdrant")
    monkeypatch.setenv("BENCH_COMPARE", "auto")


    module = _load_compare_module()

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(module, "_load_git_commit", lambda: "exitfailure")

    monkeypatch.setattr(module, "_build_dataset", lambda: (_ for _ in ()).throw(SystemExit("top-level exit")))

    exit_code = module.main()
    assert exit_code == 1

    json_payload = json.loads(module.JSON_REPORT.read_text())
    assert json_payload.get("error", "").lower().startswith("top-level exit") or "systemexit" in json_payload.get("error", "").lower()
    for entry in json_payload["targets"]:
        assert entry["skipped"] is True
        assert "exit" in entry.get("reason", "").lower()

