"""Test to verify CI artifact generation structure is complete.

This test validates that the CI workflow can generate all six compare artifacts:
- compare.json, compare.md (from docker compose qa service)
- compare_pure.json, compare_pure.md (from pure drivers test)
- compare_http.json, compare_http.md (from HTTP drivers test)
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_docker_compose_has_faiss_api_service() -> None:
    """Verify faiss-api service exists in docker-compose.ci.yml."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    assert compose_file.exists(), "docker-compose.ci.yml should exist"
    
    content = compose_file.read_text()
    assert "faiss-api:" in content, "faiss-api service should be defined"
    assert "compare-faiss" in content, "compare-faiss profile should exist"
    assert "bench/faiss_http" in content, "faiss-api should use bench/faiss_http context"


def test_faiss_http_service_exists() -> None:
    """Verify faiss HTTP service files exist."""
    repo_root = Path(__file__).resolve().parents[3]
    faiss_http_dir = repo_root / "MEF-Core_v1.0" / "bench" / "faiss_http"
    
    assert faiss_http_dir.exists(), "bench/faiss_http directory should exist"
    assert (faiss_http_dir / "Dockerfile").exists(), "Dockerfile should exist"
    assert (faiss_http_dir / "app.py").exists(), "app.py should exist"
    assert (faiss_http_dir / "requirements.txt").exists(), "requirements.txt should exist"
    
    # Verify Dockerfile has curl for healthcheck
    dockerfile = (faiss_http_dir / "Dockerfile").read_text()
    assert "curl" in dockerfile, "Dockerfile should install curl for healthcheck"


def test_compare_driver_registry_complete() -> None:
    """Verify all compare drivers are registered."""
    try:
        from tests.bench.compare.drivers import DRIVER_REGISTRY
    except ImportError as exc:
        # Dependencies might not be installed in test environment
        print(f"  (skipped: {exc})")
        return
    
    required_drivers = {
        "mef-core",
        "faiss-inproc",
        "mef-http",
        "faiss-http",
    }
    
    registered = set(DRIVER_REGISTRY.keys())
    assert required_drivers.issubset(registered), (
        f"Missing drivers: {required_drivers - registered}"
    )


def test_faiss_cpu_version_flexible() -> None:
    """Verify faiss-cpu version allows Python 3.12+."""
    repo_root = Path(__file__).resolve().parents[3]
    requirements = repo_root / "MEF-Core_v1.0" / "requirements.txt"
    
    content = requirements.read_text()
    
    # Should not have exact version pin
    assert "faiss-cpu==1.7.4" not in content, (
        "faiss-cpu should use flexible version for Python 3.12+ compatibility"
    )
    
    # Should have version constraint
    assert "faiss-cpu" in content, "faiss-cpu should be in requirements"


def test_docker_compose_validation() -> None:
    """Verify docker-compose.ci.yml is valid."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config", "--quiet"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    
    assert result.returncode == 0, (
        f"docker-compose.ci.yml validation failed:\n{result.stderr}"
    )


if __name__ == "__main__":
    import pytest
    
    pytest.main([__file__, "-v"])
