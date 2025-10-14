"""Integration tests for enterprise infrastructure features.

These tests validate the enterprise-ready configuration including:
- Environment configuration files
- Docker Compose configurations
- Network segmentation
- Resource limits
- Monitoring setup
- Secrets management configuration
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def test_environment_templates_exist() -> None:
    """Verify all environment template files exist."""
    repo_root = Path(__file__).resolve().parents[3]
    
    required_files = [
        ".env.example",
        ".env.development",
        ".env.staging",
        ".env.production",
    ]
    
    for filename in required_files:
        filepath = repo_root / filename
        assert filepath.exists(), f"Environment template {filename} must exist"
        assert filepath.stat().st_size > 0, f"{filename} must not be empty"
    
    print("✓ All environment template files exist")


def test_env_example_completeness() -> None:
    """Verify .env.example contains all required configuration."""
    repo_root = Path(__file__).resolve().parents[3]
    env_example = repo_root / ".env.example"
    
    content = env_example.read_text()
    
    required_sections = [
        "ENVIRONMENT CONFIGURATION",
        "AUTHENTICATION & SECURITY",
        "SERVICE ENDPOINTS",
        "BENCHMARK CONFIGURATION",
        "RESOURCE LIMITS",
        "LOGGING & MONITORING",
    ]
    
    for section in required_sections:
        assert section in content, f"Section '{section}' must be in .env.example"
    
    required_vars = [
        "ENVIRONMENT",
        "AUTH_TOKEN_REQUIRED",
        "QUALITY_BASE_URL",
        "QDRANT_URL",
        "MILVUS_HOST",
        "BENCH_COMPARE",
        "API_CPU_LIMIT",
        "API_MEMORY_LIMIT",
        "LOG_LEVEL",
        "ENABLE_METRICS",
    ]
    
    for var in required_vars:
        assert var in content, f"Variable '{var}' must be in .env.example"
    
    print("✓ .env.example is complete")


def test_docker_compose_ci_enterprise_features() -> None:
    """Verify docker-compose.ci.yml has enterprise features."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    # Test API service has all enterprise features
    assert "api" in services, "API service must be defined"
    api = services["api"]
    
    # Resource limits
    assert "deploy" in api, "API must have deploy configuration"
    assert "resources" in api["deploy"], "API must have resource limits"
    assert "limits" in api["deploy"]["resources"]
    assert "reservations" in api["deploy"]["resources"]
    
    # Health check
    assert "healthcheck" in api, "API must have healthcheck"
    assert "test" in api["healthcheck"]
    assert "interval" in api["healthcheck"]
    assert "retries" in api["healthcheck"]
    
    # Restart policy
    assert "restart" in api, "API must have restart policy"
    
    # Logging
    assert "logging" in api, "API must have logging configuration"
    assert api["logging"]["driver"] == "json-file"
    
    # Networks
    assert "networks" in api, "API must specify networks"
    assert "test-network" in api["networks"]
    assert "db-network" in api["networks"]
    
    print("✓ docker-compose.ci.yml has enterprise features for API")


def test_docker_compose_network_segmentation() -> None:
    """Verify network segmentation is properly configured."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    networks = compose.get("networks", {})
    
    # Check required networks exist
    assert "test-network" in networks, "test-network must be defined"
    assert "db-network" in networks, "db-network must be defined"
    
    # Check network configuration
    for network_name in ["test-network", "db-network"]:
        network = networks[network_name]
        assert network["driver"] == "bridge", f"{network_name} must use bridge driver"
        assert "name" in network, f"{network_name} must have explicit name"
        assert "ipam" in network, f"{network_name} must have IPAM config"
        assert "config" in network["ipam"]
        assert len(network["ipam"]["config"]) > 0
        assert "subnet" in network["ipam"]["config"][0]
    
    # Verify services are on correct networks
    services = compose.get("services", {})
    
    # API should be on both test and db networks
    assert "test-network" in services["api"]["networks"]
    assert "db-network" in services["api"]["networks"]
    
    # Qdrant should only be on db network
    assert "db-network" in services["qdrant"]["networks"]
    assert "test-network" not in services["qdrant"]["networks"]
    
    # Milvus should only be on db network
    assert "db-network" in services["milvus"]["networks"]
    assert "test-network" not in services["milvus"]["networks"]
    
    print("✓ Network segmentation is properly configured")


def test_all_services_have_resource_limits() -> None:
    """Verify all services have resource limits configured."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    # Services that should have resource limits
    services_with_limits = ["api", "qdrant", "milvus", "qa", "faiss-api"]
    
    for service_name in services_with_limits:
        if service_name not in services:
            continue  # Skip if service not in this compose file
        
        service = services[service_name]
        assert "deploy" in service, f"{service_name} must have deploy config"
        assert "resources" in service["deploy"], f"{service_name} must have resources"
        
        resources = service["deploy"]["resources"]
        assert "limits" in resources, f"{service_name} must have resource limits"
        assert "cpus" in resources["limits"], f"{service_name} must have CPU limit"
        assert "memory" in resources["limits"], f"{service_name} must have memory limit"
        
        assert "reservations" in resources, f"{service_name} must have reservations"
    
    print("✓ All services have resource limits")


def test_all_services_have_logging() -> None:
    """Verify all services have centralized logging configured."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    # Services that should have logging (exclude qa which is one-shot)
    services_with_logging = ["api", "qdrant", "milvus", "qa", "faiss-api"]
    
    for service_name in services_with_logging:
        if service_name not in services:
            continue
        
        service = services[service_name]
        assert "logging" in service, f"{service_name} must have logging config"
        
        logging = service["logging"]
        assert logging["driver"] == "json-file", f"{service_name} must use json-file driver"
        assert "options" in logging, f"{service_name} must have logging options"
        assert "max-size" in logging["options"]
        assert "max-file" in logging["options"]
    
    print("✓ All services have centralized logging")


def test_docker_compose_production_exists() -> None:
    """Verify production docker-compose file exists with monitoring."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.production.yml"
    
    assert compose_file.exists(), "docker-compose.production.yml must exist"
    
    with open(compose_file) as f:
        compose = yaml.safe_load(f)
    
    services = compose.get("services", {})
    
    # Check monitoring services exist
    assert "prometheus" in services, "Prometheus service must be defined"
    assert "grafana" in services, "Grafana service must be defined"
    
    # Check production API service exists
    assert "api-production" in services, "Production API service must be defined"
    
    # Check secrets support
    api_prod = services["api-production"]
    assert "secrets" in api_prod, "Production API must support secrets"
    
    # Check networks include monitoring
    networks = compose.get("networks", {})
    assert "monitoring-network" in networks, "Monitoring network must be defined"
    
    # Check volumes for persistence
    volumes = compose.get("volumes", {})
    assert "prometheus-data" in volumes, "Prometheus data volume must be defined"
    assert "grafana-data" in volumes, "Grafana data volume must be defined"
    
    print("✓ docker-compose.production.yml is properly configured")


def test_monitoring_configuration_exists() -> None:
    """Verify monitoring configuration files exist."""
    repo_root = Path(__file__).resolve().parents[3]
    monitoring_dir = repo_root / "monitoring"
    
    assert monitoring_dir.exists(), "monitoring/ directory must exist"
    
    # Check Prometheus config
    prometheus_yml = monitoring_dir / "prometheus.yml"
    assert prometheus_yml.exists(), "prometheus.yml must exist"
    
    with open(prometheus_yml) as f:
        prom_config = yaml.safe_load(f)
        assert "scrape_configs" in prom_config
        assert len(prom_config["scrape_configs"]) > 0
    
    # Check Grafana datasource config
    grafana_datasource = monitoring_dir / "grafana" / "datasources" / "prometheus.yml"
    assert grafana_datasource.exists(), "Grafana datasource config must exist"
    
    # Check Grafana dashboard provider
    grafana_dashboard = monitoring_dir / "grafana" / "dashboards" / "dashboard-provider.yml"
    assert grafana_dashboard.exists(), "Grafana dashboard provider must exist"
    
    print("✓ Monitoring configuration files exist")


def test_infrastructure_documentation_exists() -> None:
    """Verify comprehensive infrastructure documentation exists."""
    repo_root = Path(__file__).resolve().parents[3]
    
    # Check main infrastructure doc
    infra_doc = repo_root / "INFRASTRUCTURE.md"
    assert infra_doc.exists(), "INFRASTRUCTURE.md must exist"
    
    content = infra_doc.read_text()
    
    required_sections = [
        "Network Segmentation",
        "Service Configuration",
        "Resource Management",
        "Monitoring & Observability",
        "Security & Secrets Management",
        "Environment Configuration",
        "Deployment Procedures",
        "Troubleshooting",
        "CI/CD Pipeline",
    ]
    
    for section in required_sections:
        assert section in content, f"Section '{section}' must be in INFRASTRUCTURE.md"
    
    # Check secrets management doc
    secrets_doc = repo_root / "SECRETS_MANAGEMENT.md"
    assert secrets_doc.exists(), "SECRETS_MANAGEMENT.md must exist"
    
    secrets_content = secrets_doc.read_text()
    assert "Docker Secrets" in secrets_content
    assert "HashiCorp Vault" in secrets_content
    assert "AWS Secrets Manager" in secrets_content
    
    print("✓ Infrastructure documentation is comprehensive")


def test_ci_workflow_has_retry_logic() -> None:
    """Verify CI workflow has retry logic and error handling."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    with open(ci_file) as f:
        ci_content = f.read()
    
    # Check for retry function
    assert "retry_with_backoff" in ci_content, "CI must have retry_with_backoff function"
    
    # Check for error handling
    assert "max_attempts" in ci_content, "CI must have max retry attempts"
    assert "timeout" in ci_content, "CI must have timeouts"
    
    # Check for comprehensive logging on error
    assert "--tail" in ci_content, "CI must capture logs on failure"
    assert "Container status:" in ci_content, "CI must show container status on failure"
    
    # Check for environment documentation
    assert "ENVIRONMENT CONFIGURATION" in ci_content, "CI must document environment variables"
    
    print("✓ CI workflow has enterprise-grade retry logic and error handling")


def test_gitignore_configured_for_env_files() -> None:
    """Verify .gitignore properly handles environment files."""
    repo_root = Path(__file__).resolve().parents[3]
    gitignore = repo_root / ".gitignore"
    
    with open(gitignore) as f:
        content = f.read()
    
    # Check that .env is ignored
    assert ".env" in content, ".env must be in .gitignore"
    
    # Check that templates are not ignored
    assert "!.env.example" in content, ".env.example must not be ignored"
    assert "!.env.development" in content, ".env.development must not be ignored"
    
    print("✓ .gitignore properly configured for environment files")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
