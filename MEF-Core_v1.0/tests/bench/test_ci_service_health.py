"""Tests for CI service health checks and dependency verification.

These tests validate that the CI configuration properly checks for
service health and dependencies before running benchmarks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_docker_compose_health_checks() -> None:
    """Verify all services have proper health checks configured."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    assert compose_file.exists(), "docker-compose.ci.yml must exist"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    
    # Check API service has healthcheck
    assert "api" in services, "API service must be defined"
    assert "healthcheck" in services["api"], "API must have healthcheck"
    assert "test" in services["api"]["healthcheck"], "API healthcheck must have test"
    
    # Check Qdrant service has healthcheck
    assert "qdrant" in services, "Qdrant service must be defined"
    assert "healthcheck" in services["qdrant"], "Qdrant must have healthcheck"
    
    # Check Milvus service has healthcheck
    assert "milvus" in services, "Milvus service must be defined"
    assert "healthcheck" in services["milvus"], "Milvus must have healthcheck"
    
    print("✓ All required services have healthchecks configured")


def test_qa_service_dependencies() -> None:
    """Verify QA service waits for all services to be healthy."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    qa_service = services.get("qa", {})
    
    assert "depends_on" in qa_service, "QA service must have depends_on"
    depends_on = qa_service["depends_on"]
    
    # Check API dependency
    assert "api" in depends_on, "QA must depend on API"
    assert depends_on["api"]["condition"] == "service_healthy", \
        "QA must wait for API to be healthy"
    
    # Check Qdrant dependency - CRITICAL FIX
    assert "qdrant" in depends_on, "QA must depend on Qdrant"
    assert depends_on["qdrant"]["condition"] == "service_healthy", \
        "QA must wait for Qdrant to be healthy (not just started)"
    
    # Check Milvus dependency
    assert "milvus" in depends_on, "QA must depend on Milvus"
    assert depends_on["milvus"]["condition"] == "service_healthy", \
        "QA must wait for Milvus to be healthy"
    
    print("✓ QA service properly depends on all services being healthy")


def test_qa_service_dependency_verification() -> None:
    """Verify QA service checks for required Python packages via preflight check."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_content = f.read()
    
    # Check for preflight validation step
    assert "preflight_check.py" in compose_content, \
        "QA service must run preflight_check.py to validate environment"
    
    # Check for error handling on preflight failure
    assert "Pre-flight validation failed" in compose_content or "ERROR: Pre-flight" in compose_content, \
        "QA service must handle preflight check failures"
    
    print("✓ QA service uses comprehensive preflight validation")


def test_ci_workflow_service_verification() -> None:
    """Verify CI workflow has explicit service health verification step."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    assert ci_file.exists(), "CI workflow file must exist"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for preflight validation step
    assert "pre-flight" in ci_content.lower() or "preflight" in ci_content.lower(), \
        "CI must have pre-flight environment validation step"
    
    assert "preflight_check.py" in ci_content, \
        "CI must run preflight_check.py to validate environment"
    
    # Check for service verification step
    assert "Start services and verify health" in ci_content, \
        "CI must have explicit service health verification step"
    
    # Check for API health verification
    assert "curl -fsS http://localhost:8080/healthz" in ci_content, \
        "CI must verify API health endpoint"
    
    # Check for Qdrant health verification
    assert "curl -fsS http://localhost:6333/readyz" in ci_content, \
        "CI must verify Qdrant readyz endpoint"
    
    # Check for Milvus health verification
    assert "curl -fsS http://localhost:9091/healthz" in ci_content, \
        "CI must verify Milvus healthz endpoint"
    
    # Check for fail-fast error handling
    assert "ERROR: API service failed to become healthy" in ci_content, \
        "CI must fail fast with clear error if API doesn't start"
    assert "ERROR: Qdrant service failed to become healthy" in ci_content, \
        "CI must fail fast with clear error if Qdrant doesn't start"
    assert "ERROR: Milvus service failed to become healthy" in ci_content, \
        "CI must fail fast with clear error if Milvus doesn't start"
    
    print("✓ CI workflow has proper service health verification and preflight checks")


def test_ci_workflow_output_validation() -> None:
    """Verify CI workflow validates all required output files."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for required file validation
    required_files = [
        "assets/bench/bench_report.json",
        "assets/bench/recall_report.json",
        "assets/bench/server.log",
        "assets/bench/compare.json",
        "assets/bench/compare.md",
    ]
    
    for file_path in required_files:
        assert file_path in ci_content, \
            f"CI must validate {file_path} exists"
    
    # Check for error messages about missing files
    assert "ERROR: Required file" in ci_content, \
        "CI must have clear error messages for missing files"
    
    # Check for non-empty file validation
    assert "exists but is empty" in ci_content, \
        "CI must validate files are non-empty"
    
    print("✓ CI workflow validates all required output files")


def test_pymilvus_in_requirements() -> None:
    """Verify pymilvus is in requirements.txt."""
    repo_root = Path(__file__).resolve().parents[2]
    requirements_file = repo_root / "requirements.txt"
    
    assert requirements_file.exists(), "requirements.txt must exist"
    
    with open(requirements_file) as f:
        requirements = f.read()
    
    assert "pymilvus" in requirements, \
        "pymilvus must be in requirements.txt"
    
    # Verify version is specified
    assert "pymilvus==" in requirements or "pymilvus>=" in requirements, \
        "pymilvus version must be specified"
    
    print("✓ pymilvus is properly specified in requirements.txt")


def test_ci_workflow_timeout_values() -> None:
    """Verify CI workflow has appropriate timeout values for services."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for timeout commands
    assert "timeout 120" in ci_content, \
        "CI must have timeout for API/Qdrant services"
    
    assert "timeout 180" in ci_content, \
        "CI must have longer timeout for Milvus (standalone mode)"
    
    print("✓ CI workflow has appropriate timeout values")


def test_docker_compose_milvus_configuration() -> None:
    """Verify Milvus is properly configured for CI."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    milvus = services.get("milvus", {})
    
    # Check Milvus is using standalone mode
    assert "command" in milvus, "Milvus must have command specified"
    command = milvus["command"]
    assert "standalone" in " ".join(command), \
        "Milvus must run in standalone mode (includes all components)"
    
    # Check ports are exposed
    assert "ports" in milvus, "Milvus must expose ports"
    ports = milvus["ports"]
    port_strings = [str(p) for p in ports]
    assert any("19530" in p for p in port_strings), \
        "Milvus must expose gRPC port 19530"
    assert any("9091" in p for p in port_strings), \
        "Milvus must expose health/metrics port 9091"
    
    # Check healthcheck uses the health endpoint
    assert "healthcheck" in milvus, "Milvus must have healthcheck"
    healthcheck = milvus["healthcheck"]
    test_cmd = " ".join(healthcheck["test"])
    assert "9091/healthz" in test_cmd, \
        "Milvus healthcheck must use port 9091 /healthz endpoint"
    
    print("✓ Milvus is properly configured for CI")


def test_ci_resource_limits_for_runners() -> None:
    """Verify all services have CPU limits ≤2.0 for CI runners."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    
    # Check all services with resource limits
    for service_name in ["api", "qdrant", "milvus", "qa"]:
        if service_name not in services:
            continue
            
        service = services[service_name]
        
        # Check if deploy/resources/limits/cpus exists
        if "deploy" in service and "resources" in service["deploy"]:
            limits = service["deploy"]["resources"].get("limits", {})
            
            # CPU limit should be a string like "${VAR:-2.0}" or just "2.0"
            cpu_limit = limits.get("cpus", "")
            
            # Extract the default value from ${VAR:-default} pattern
            if ":-" in cpu_limit:
                default_val = cpu_limit.split(":-")[1].rstrip("}")
            else:
                default_val = cpu_limit
            
            # Convert to float and check
            if default_val:
                try:
                    cpu_val = float(default_val)
                    assert cpu_val <= 2.0, \
                        f"{service_name} CPU limit ({cpu_val}) exceeds 2.0 cores for CI runner"
                    print(f"✓ {service_name} CPU limit: {cpu_val} (within CI constraints)")
                except ValueError:
                    pass  # Skip if can't parse
    
    print("✓ All services have appropriate CPU limits for CI runners")


def test_health_check_retry_parameters() -> None:
    """Verify health checks have robust retry parameters."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    
    # Check API health check
    api_hc = services["api"]["healthcheck"]
    assert api_hc["interval"] == "3s", "API healthcheck interval should be 3s"
    assert api_hc["timeout"] == "5s", "API healthcheck timeout should be 5s"
    assert api_hc["retries"] >= 60, "API healthcheck should have ≥60 retries"
    print("✓ API has robust health check configuration")
    
    # Check Qdrant health check
    qdrant_hc = services["qdrant"]["healthcheck"]
    assert qdrant_hc["interval"] == "2s", "Qdrant healthcheck interval should be 2s"
    assert qdrant_hc["timeout"] == "5s", "Qdrant healthcheck timeout should be 5s"
    assert qdrant_hc["retries"] >= 90, "Qdrant healthcheck should have ≥90 retries"
    print("✓ Qdrant has robust health check configuration")
    
    # Check Milvus health check
    milvus_hc = services["milvus"]["healthcheck"]
    assert milvus_hc["interval"] == "3s", "Milvus healthcheck interval should be 3s"
    assert milvus_hc["timeout"] == "5s", "Milvus healthcheck timeout should be 5s"
    assert milvus_hc["retries"] >= 80, "Milvus healthcheck should have ≥80 retries"
    assert "start_period" in milvus_hc, "Milvus healthcheck should have start_period"
    print("✓ Milvus has robust health check configuration")


def test_ci_post_benchmark_verification() -> None:
    """Verify CI workflow has post-benchmark service verification."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for post-benchmark verification step
    assert "Verify services still healthy (post-benchmark)" in ci_content, \
        "CI must have post-benchmark service verification step"
    
    assert "Post-Benchmark Service Verification" in ci_content, \
        "CI must include post-benchmark verification logging"
    
    # Check it verifies all three services
    assert "Check API" in ci_content and "API health endpoint responding" in ci_content, \
        "CI must verify API after benchmarks"
    assert "Check Qdrant" in ci_content and "Qdrant readyz endpoint responding" in ci_content, \
        "CI must verify Qdrant after benchmarks"
    assert "Check Milvus" in ci_content and "Milvus healthz endpoint responding" in ci_content, \
        "CI must verify Milvus after benchmarks"
    
    # Check it reports summary
    assert "Services online and accessible" in ci_content, \
        "CI must report service verification summary"
    
    print("✓ CI workflow includes post-benchmark service verification")


def test_ci_enhanced_retry_logic() -> None:
    """Verify CI workflow has enhanced retry logic with better backoff."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for enhanced retry function
    assert "retry_with_backoff()" in ci_content, \
        "CI must have retry_with_backoff function"
    
    # Check it has max_attempts parameter
    assert "max_attempts=" in ci_content, \
        "Retry function must define max_attempts"
    
    # Check it has exponential backoff
    assert "timeout=$((timeout * 2))" in ci_content, \
        "Retry function must implement exponential backoff"
    
    # Check it has better logging
    assert "Attempt $attempt/$max_attempts" in ci_content, \
        "Retry function must log attempt numbers"
    
    print("✓ CI workflow has enhanced retry logic with exponential backoff")


def test_docker_compose_milvus_configuration() -> None:
    """Verify Milvus is properly configured for CI."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose_config = yaml.safe_load(f)
    
    services = compose_config.get("services", {})
    milvus = services.get("milvus", {})
    
    # Check Milvus is using standalone mode
    assert "command" in milvus, "Milvus must have command specified"
    command = milvus["command"]
    assert "standalone" in " ".join(command), \
        "Milvus must run in standalone mode (includes all components)"
    
    # Check ports are exposed
    assert "ports" in milvus, "Milvus must expose ports"
    ports = milvus["ports"]
    port_strings = [str(p) for p in ports]
    
    # Check gRPC port (19530) is exposed
    assert any("19530" in str(p) for p in ports), \
        "Milvus must expose port 19530 (gRPC)"
    
    # Check health port (9091) is exposed
    assert any("9091" in str(p) for p in ports), \
        "Milvus must expose port 9091 (health)"
    
    # Check environment variables for standalone mode
    env = milvus.get("environment", {})
    assert "ETCD_USE_EMBED" in env or any("ETCD_USE_EMBED" in str(e) for e in env), \
        "Milvus must use embedded etcd for standalone mode"
    
    print("✓ Milvus is properly configured for CI (standalone mode)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
