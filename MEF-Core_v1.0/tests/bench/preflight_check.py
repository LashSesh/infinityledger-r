#!/usr/bin/env python3
"""Pre-flight validation script for CI/CD environment.

This script validates all required environment variables and dependencies
before running the main benchmark/test suite, providing clear error messages
and failing fast if configuration is invalid.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directories to path
SCRIPT_DIR = Path(__file__).resolve().parent
MEF_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(MEF_ROOT))
sys.path.insert(0, str(MEF_ROOT / "src"))

from tests.bench.env_validator import (
    EnvValidationError,
    validate_positive_int,
    validate_positive_float,
    validate_url,
    validate_bool,
    validate_comma_list,
    print_env_config,
)


def validate_all_env_vars() -> Dict[str, Any]:
    """Validate all environment variables used by the benchmark suite.
    
    Returns:
        Dictionary of validated configuration values
        
    Raises:
        EnvValidationError: If any validation fails
        SystemExit: On fatal validation errors
    """
    config: Dict[str, Any] = {}
    
    try:
        # Benchmark configuration
        config["BENCH_POINTS"] = validate_positive_int(
            "BENCH_POINTS",
            default=100000,
            min_value=100,
            max_value=10000000,
        )
        
        config["BENCH_Q"] = validate_positive_int(
            "BENCH_Q",
            default=200,
            min_value=1,
            max_value=10000,
        )
        
        config["BENCH_K"] = validate_positive_int(
            "BENCH_K",
            default=10,
            min_value=1,
            max_value=1000,
        )
        
        config["UPSERT_BATCH"] = validate_positive_int(
            "UPSERT_BATCH",
            default=2000,
            min_value=1,
            max_value=10000,
        )
        
        config["BENCH_TIMEOUT_SECONDS"] = validate_positive_float(
            "BENCH_TIMEOUT_SECONDS",
            default=1200.0,
            min_value=10.0,
            max_value=7200.0,
        )
        
        config["COMPARE_LIMIT"] = validate_positive_int(
            "COMPARE_LIMIT",
            default=500,
            min_value=0,
        )
        
        # Recall configuration
        config["RECALL_EFSEARCH"] = validate_positive_int(
            "RECALL_EFSEARCH",
            default=128,
            min_value=1,
            max_value=1000,
        )
        
        config["HNSW_EF_SEARCH"] = validate_positive_int(
            "HNSW_EF_SEARCH",
            default=64,
            min_value=1,
            max_value=1000,
        )
        
        # Golden test configuration
        config["GOLDEN_COUNT"] = validate_positive_int(
            "GOLDEN_COUNT",
            default=30,
            min_value=1,
            max_value=1000,
        )
        
        config["GOLDEN_MIN_OK"] = validate_positive_int(
            "GOLDEN_MIN_OK",
            default=10,
            min_value=1,
        )
        
        config["GOLDEN_ATTEMPTS_FACTOR"] = validate_positive_int(
            "GOLDEN_ATTEMPTS_FACTOR",
            default=8,
            min_value=1,
            max_value=100,
        )
        
        config["GOLDEN_SEED"] = validate_positive_int(
            "GOLDEN_SEED",
            default=1337,
            min_value=0,
        )
        
        # Connection configuration
        config["BENCH_CONNECT_TIMEOUT"] = validate_positive_float(
            "BENCH_CONNECT_TIMEOUT",
            default=240.0,
            min_value=1.0,
            max_value=600.0,
        )
        
        config["BENCH_CONNECT_RETRY_DELAY"] = validate_positive_float(
            "BENCH_CONNECT_RETRY_DELAY",
            default=2.0,
            min_value=0.1,
            max_value=60.0,
        )
        
        config["HTTPX_TIMEOUT"] = validate_positive_float(
            "HTTPX_TIMEOUT",
            default=30.0,
            min_value=1.0,
            max_value=300.0,
        )
        
        # Service URLs
        config["QUALITY_BASE_URL"] = validate_url(
            "QUALITY_BASE_URL",
            default="http://api:8080",
            schemes=["http", "https"],
        )
        
        config["MEF_BASE_URL"] = validate_url(
            "MEF_BASE_URL",
            default="http://localhost:8080",
            schemes=["http", "https"],
        )
        
        config["QDRANT_URL"] = validate_url(
            "QDRANT_URL",
            default="http://qdrant:6333",
            schemes=["http", "https"],
        )
        
        config["FAISS_URL"] = validate_url(
            "FAISS_URL",
            default="http://localhost:8090",
            schemes=["http", "https"],
        )
        
        # Milvus configuration
        milvus_host = os.getenv("MILVUS_HOST", "milvus").strip()
        if not milvus_host:
            raise EnvValidationError("MILVUS_HOST", "cannot be empty")
        config["MILVUS_HOST"] = milvus_host
        
        config["MILVUS_PORT"] = validate_positive_int(
            "MILVUS_PORT",
            default=19530,
            min_value=1,
            max_value=65535,
        )
        
        # Boolean flags
        config["AUTH_TOKEN_REQUIRED"] = validate_bool(
            "AUTH_TOKEN_REQUIRED",
            default=False,
        )
        
        config["STRICT_READPATH"] = validate_bool(
            "STRICT_READPATH",
            default=True,
        )
        
        config["BENCH_COMPARE"] = validate_bool(
            "BENCH_COMPARE",
            default=True,
        )
        
        # Target lists
        all_known_targets = [
            "mef", "mef-core", "mef-http",
            "faiss", "faiss-inproc", "faiss-http",
            "qdrant", "milvus",
            "weaviate", "elasticsearch", "pinecone",
        ]
        
        config["TARGETS"] = validate_comma_list(
            "TARGETS",
            default=["mef", "faiss", "qdrant", "milvus"],
            allowed_values=all_known_targets,
        )
        
        config["BENCH_TARGETS"] = validate_comma_list(
            "BENCH_TARGETS",
            default=["mef", "faiss", "qdrant", "milvus"],
            allowed_values=all_known_targets,
        )
        
        config["REQUIRED_TARGETS"] = validate_comma_list(
            "REQUIRED_TARGETS",
            default=["mef", "faiss", "qdrant"],
            allowed_values=all_known_targets,
        )
        
        # Token values (optional, just check they exist)
        config["MEF_API_TOKEN"] = os.getenv("MEF_API_TOKEN", "")
        config["QUALITY_TOKEN"] = os.getenv("QUALITY_TOKEN", "")
        
        # Additional optional configuration
        config["GOLDEN_HOLD_POLICY"] = os.getenv("GOLDEN_HOLD_POLICY", "skip")
        config["QUALITY_COLLECTION"] = os.getenv("QUALITY_COLLECTION", "quality")
        config["ANN_METRIC"] = os.getenv("ANN_METRIC", "cosine")
        
        return config
        
    except EnvValidationError as exc:
        print(f"ERROR: Environment validation failed", file=sys.stderr)
        print(f"  Variable: {exc.variable}", file=sys.stderr)
        print(f"  Reason: {exc.reason}", file=sys.stderr)
        print(f"\nPlease check your environment configuration and try again.", file=sys.stderr)
        raise SystemExit(1) from exc


def check_python_dependencies() -> None:
    """Check that all required Python packages are installed.
    
    Raises:
        SystemExit: If required packages are missing
    """
    required_packages = [
        ("numpy", "numpy"),
        ("requests", "requests"),
        ("pytest", "pytest"),
        ("yaml", "pyyaml"),
        ("pymilvus", "pymilvus"),
        ("qdrant_client", "qdrant-client"),
        ("faiss", "faiss-cpu"),
    ]
    
    missing = []
    
    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    
    if missing:
        print(f"ERROR: Missing required Python packages:", file=sys.stderr)
        for pkg in missing:
            print(f"  - {pkg}", file=sys.stderr)
        print(f"\nInstall with: pip install {' '.join(missing)}", file=sys.stderr)
        raise SystemExit(1)
    
    print("✓ All required Python packages are installed")


def check_directory_structure() -> None:
    """Check that required directories exist and are writable.
    
    Raises:
        SystemExit: If directory structure is invalid
    """
    assets_dir = MEF_ROOT / "assets" / "bench"
    golden_dir = MEF_ROOT / "assets" / "golden"
    
    for directory in [assets_dir, golden_dir]:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # Test write access
            test_file = directory / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except (OSError, PermissionError) as exc:
            print(f"ERROR: Cannot write to directory {directory}", file=sys.stderr)
            print(f"  Reason: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    
    print(f"✓ Directory structure is valid and writable")


def main() -> int:
    """Main entry point for pre-flight validation.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    print("=" * 60)
    print("CI/CD Pre-Flight Environment Validation")
    print("=" * 60)
    print()
    
    # Step 1: Validate environment variables
    print("[1/3] Validating environment variables...")
    try:
        config = validate_all_env_vars()
        print(f"✓ All environment variables validated")
        print()
        print_env_config(config, prefix="  ")
        print()
    except SystemExit:
        return 1
    
    # Step 2: Check Python dependencies
    print("[2/3] Checking Python dependencies...")
    try:
        check_python_dependencies()
        print()
    except SystemExit:
        return 1
    
    # Step 3: Check directory structure
    print("[3/3] Checking directory structure...")
    try:
        check_directory_structure()
        print()
    except SystemExit:
        return 1
    
    print("=" * 60)
    print("✓ All pre-flight checks passed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
