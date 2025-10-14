"""End-to-end regression test for the compare runner."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from bench.drivers.base import VectorStoreDriver


class _SuccessfulDriver(VectorStoreDriver):
    def __init__(self, name: str, metric: str = "cosine") -> None:
        super().__init__(metric)
        self.name = name

    def connect(self) -> None:  # pragma: no cover - deterministic stub
        return None

    def clear(self, namespace: str) -> None:  # pragma: no cover - deterministic stub
        return None

    def upsert(self, items, namespace: str, batch_size: int = 1000) -> None:  # pragma: no cover
        return None

    def search(self, query, k: int, namespace: str):  # pragma: no cover - deterministic stub
        return [(f"{self.name}-hit", 0.99)]


@pytest.mark.parametrize(
    "targets",
    ["mef,faiss,qdrant,milvus"],
)
def test_compare_runner_creates_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, targets: str
) -> None:
    monkeypatch.setenv("BENCH_COMPARE", "1")
    monkeypatch.setenv("TARGETS", targets)
    monkeypatch.setenv("COMPARE_LIMIT", "5")

    # Import compare.py directly instead of through the package
    import importlib.util
    import sys
    compare_py_path = Path(__file__).parent / "compare.py"
    spec = importlib.util.spec_from_file_location("_test_compare_module", compare_py_path)
    assert spec and spec.loader, "Could not load compare.py"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "ASSETS_DIR", tmp_path)
    monkeypatch.setattr(module, "JSON_REPORT", tmp_path / "compare.json")
    monkeypatch.setattr(module, "MARKDOWN_REPORT", tmp_path / "compare.md")
    monkeypatch.setattr(
        module,
        "_build_dataset",
        lambda: (
            [
                ("id-1", [0.1, 0.2, 0.3], {"index": 0}),
                ("id-2", [0.2, 0.3, 0.4], {"index": 1}),
            ],
            3,
        ),
    )
    monkeypatch.setattr(module, "_build_queries", lambda _corpus: [[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]])
    monkeypatch.setattr(module, "_prepare_oracle", lambda _items, _queries: [["id-1"], ["id-2"]])
    monkeypatch.setattr(module, "_load_git_commit", lambda: "e2e-commit")

    module.TARGET_REGISTRY = {
        "mef": lambda metric="cosine": _SuccessfulDriver("MEF", metric),
        "faiss": lambda metric="cosine": _SuccessfulDriver("FAISS", metric),
        "qdrant": lambda metric="cosine": _SuccessfulDriver("Qdrant", metric),
        "milvus": lambda metric="cosine": _SuccessfulDriver("Milvus", metric),
    }

    exit_code = module.main()
    assert exit_code == 0

    assert module.JSON_REPORT.exists()
    assert module.MARKDOWN_REPORT.exists()

    json_payload = json.loads(module.JSON_REPORT.read_text())
    ok_targets = [entry for entry in json_payload["targets"] if entry["status"] == "ok"]
    assert len(ok_targets) >= 2
    assert "errors" not in json_payload

    markdown = module.MARKDOWN_REPORT.read_text()
    assert "| MEF | ok |" in markdown
    assert "| Qdrant | ok |" in markdown or "| Milvus | ok |" in markdown
