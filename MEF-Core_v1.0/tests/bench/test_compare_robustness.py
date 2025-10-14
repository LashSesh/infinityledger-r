"""Test to verify compare module robustness and artifact generation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add MEF-Core to path for direct script execution
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


def test_compare_module_always_provides_main():
    """Verify that compare module always exports a callable main() function."""
    # This should never fail, even if compare.py has import errors
    from tests.bench.compare import main
    
    assert callable(main), "main should always be callable"
    print("✓ compare module provides callable main()")


def test_compare_module_execution_creates_artifacts():
    """Verify that running compare module creates artifacts even on failure."""
    repo_root = Path(__file__).resolve().parents[2]
    assets_dir = repo_root / "assets" / "bench"
    json_report = assets_dir / "compare.json"
    md_report = assets_dir / "compare.md"
    
    # Clean up any existing artifacts
    for path in (json_report, md_report):
        if path.exists():
            path.unlink()
    
    # Import and run main()
    from tests.bench.compare import main
    exit_code = main()
    
    # Verify artifacts were created
    assert json_report.exists(), "compare.json should be created"
    assert md_report.exists(), "compare.md should be created"
    assert json_report.stat().st_size > 0, "compare.json should not be empty"
    assert md_report.stat().st_size > 0, "compare.md should not be empty"
    
    # Verify JSON content is valid
    payload = json.loads(json_report.read_text())
    assert "status" in payload or "results" in payload, "JSON should have status or results"
    
    print(f"✓ Artifacts created with exit code {exit_code}")
    print(f"  - compare.json: {json_report.stat().st_size} bytes")
    print(f"  - compare.md: {md_report.stat().st_size} bytes")
    
    # Clean up
    for path in (json_report, md_report):
        if path.exists():
            path.unlink()


def test_compare_module_via_main():
    """Test that python -m tests.bench.compare can be executed."""
    import importlib.util
    
    spec = importlib.util.find_spec("tests.bench.compare.__main__")
    assert spec is not None, "tests.bench.compare.__main__ should be importable"
    
    from tests.bench.compare import main
    assert callable(main), "main should be callable from package"
    
    print("✓ compare module can be executed via python -m")


if __name__ == "__main__":
    print("Running compare module robustness tests...\n")
    
    try:
        test_compare_module_always_provides_main()
        test_compare_module_execution_creates_artifacts()
        test_compare_module_via_main()
        print("\n✅ All tests passed!")
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
