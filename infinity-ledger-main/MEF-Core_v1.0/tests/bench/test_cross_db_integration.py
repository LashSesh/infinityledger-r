"""Integration tests for cross-database benchmarking.

These tests validate the cross-DB benchmarking infrastructure
comprehensively to ensure enterprise-ready functionality.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


def test_compare_pure_drivers_e2e() -> None:
    """Test pure drivers (mef-core, faiss-inproc) end-to-end."""
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / "assets" / "bench"
    
    # Clean up old reports
    for report in ["compare.json", "compare.md"]:
        path = assets_dir / report
        if path.exists():
            path.unlink()
    
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"{repo_root}/src:{repo_root}",
        "BENCH_COMPARE": "1",
        "TARGETS": "mef-core,faiss-inproc",
        "COMPARE_LIMIT": "32",
        "BENCH_K": "5",
    })
    
    result = subprocess.run(
        ["python", "-m", "tests.bench.compare"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    
    assert result.returncode == 0, f"Compare failed: {result.stderr}"
    
    # Validate outputs
    json_report = assets_dir / "compare.json"
    md_report = assets_dir / "compare.md"
    
    assert json_report.exists(), "JSON report should be created"
    assert md_report.exists(), "Markdown report should be created"
    
    payload = json.loads(json_report.read_text())
    assert "commit" in payload
    assert "dataset" in payload
    assert "targets" in payload
    
    targets = payload["targets"]
    ok_targets = [t for t in targets if t.get("status") == "ok"]
    
    assert len(ok_targets) >= 2, f"Expected >=2 successful targets, got {len(ok_targets)}"
    print(f"✓ Pure drivers E2E test passed with {len(ok_targets)} successful targets")


def test_external_drivers_skip_gracefully() -> None:
    """Test that unavailable external services are skipped gracefully."""
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / "assets" / "bench"
    
    # Clean up old reports
    for report in ["compare.json", "compare.md"]:
        path = assets_dir / report
        if path.exists():
            path.unlink()
    
    env = os.environ.copy()
    env.update({
        "PYTHONPATH": f"{repo_root}/src:{repo_root}",
        "BENCH_COMPARE": "1",
        "TARGETS": "mef-core,faiss-inproc,qdrant,milvus",  # qdrant and milvus won't be running
        "COMPARE_LIMIT": "16",
        "BENCH_CONNECT_TIMEOUT": "5",  # Short timeout
        "BENCH_CONNECT_RETRY_DELAY": "1",
    })
    
    result = subprocess.run(
        ["python", "-m", "tests.bench.compare"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    
    # Should still exit 0 because we have 2 successful targets
    assert result.returncode == 0, f"Compare should succeed with partial targets: {result.stderr}"
    
    json_report = assets_dir / "compare.json"
    assert json_report.exists()
    
    payload = json.loads(json_report.read_text())
    targets = payload["targets"]
    
    # Check qdrant is skipped
    qdrant = next((t for t in targets if "qdrant" in t.get("name", "").lower()), None)
    if qdrant:
        assert qdrant.get("skipped") or qdrant.get("status") != "ok"
        print(f"✓ Qdrant properly skipped: {qdrant.get('reason', 'no reason')}")
    
    # Check milvus is skipped (not running)
    milvus = next((t for t in targets if "milvus" in t.get("name", "").lower()), None)
    if milvus:
        assert milvus.get("skipped") or milvus.get("status") != "ok"
        print(f"✓ Milvus properly skipped: {milvus.get('reason', 'no reason')}")
    
    # But we should have successful mef-core and faiss-inproc
    ok_targets = [t for t in targets if t.get("status") == "ok"]
    assert len(ok_targets) >= 2
    print(f"✓ External driver skip test passed with {len(ok_targets)} successful targets")


def test_ci_workflow_configuration() -> None:
    """Verify CI workflow has proper configuration."""
    repo_root = Path(__file__).resolve().parents[3]  # Up to infinity-ledger root
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    compose_file = repo_root / "docker-compose.ci.yml"
    
    assert ci_file.exists(), "CI workflow should exist"
    
    ci_content = ci_file.read_text()
    compose_content = compose_file.read_text()
    
    # Check required environment variables in CI
    required_vars = [
        "BENCH_COMPARE",
        "TARGETS",
        "COMPARE_LIMIT",
        "REQUIRED_TARGETS",
        "QDRANT_URL",
    ]
    
    for var in required_vars:
        assert var in ci_content, f"CI should configure {var}"
    
    # Check compare step exists in docker-compose (which is called by CI)
    # Verify it's invoked as a module (-m flag)
    assert "python -u -m tests.bench.compare" in compose_content or "python -m tests.bench.compare" in compose_content, \
        "Docker compose should invoke compare module"
    
    # Check artifacts upload in CI
    assert "compare.json" in ci_content
    assert "compare.md" in ci_content
    
    print("✓ CI workflow properly configured")


def test_docker_compose_services() -> None:
    """Verify docker-compose has required services."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    assert compose_file.exists(), "docker-compose.ci.yml should exist"
    
    content = compose_file.read_text()
    
    # Check required services
    assert "faiss-api:" in content
    assert "qdrant:" in content
    assert "qa:" in content
    assert "api:" in content
    
    # Check profiles
    assert "compare" in content
    assert "compare-faiss" in content
    
    print("✓ Docker compose services configured")


def test_readme_documentation_complete() -> None:
    """Verify README has comprehensive documentation."""
    repo_root = Path(__file__).resolve().parents[2]
    readme = repo_root / "README_bench.md"
    
    assert readme.exists(), "README_bench.md should exist"
    
    content = readme.read_text()
    
    # Check key sections
    assert "Cross-DB Compare" in content or "cross-database" in content.lower()
    assert "Environment Variables" in content
    assert "Running in GitHub Actions" in content or "CI" in content
    
    # Check key environment variables documented
    for var in ["BENCH_COMPARE", "TARGETS", "COMPARE_LIMIT"]:
        assert var in content, f"{var} should be documented"
    
    print("✓ Documentation is comprehensive")


def test_enterprise_documentation_exists() -> None:
    """Verify enterprise documentation is available."""
    repo_root = Path(__file__).resolve().parents[2]
    enterprise_doc = repo_root / "ENTERPRISE_BENCHMARKING.md"
    
    assert enterprise_doc.exists(), "ENTERPRISE_BENCHMARKING.md should exist"
    
    content = enterprise_doc.read_text()
    
    # Check key sections
    required_sections = [
        "Architecture",
        "Configuration",
        "Deployment Scenarios",
        "Failure Handling",
        "Troubleshooting",
        "Performance Tuning",
        "Best Practices",
    ]
    
    for section in required_sections:
        assert section in content, f"Enterprise doc should have {section} section"
    
    # Check database coverage
    databases = ["qdrant", "milvus", "weaviate", "elastic", "pinecone"]
    for db in databases:
        assert db in content.lower(), f"Enterprise doc should cover {db}"
    
    print("✓ Enterprise documentation is comprehensive")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
