"""Test that the compare package can be imported and executed as a module."""

from __future__ import annotations

import importlib.util


def test_compare_package_has_main():
    """Verify that the compare package exports a main function."""
    from tests.bench.compare import main
    
    assert callable(main), "main should be a callable function"


def test_compare_main_can_be_imported_from_init():
    """Verify that tests.bench.compare.__main__ can import main."""
    # This simulates what happens when running: python -m tests.bench.compare
    
    # Try to import the __main__ module without executing it
    spec = importlib.util.find_spec("tests.bench.compare.__main__")
    assert spec is not None, "tests.bench.compare.__main__ should be importable"
    
    # The actual main function should be available
    from tests.bench.compare import main
    assert callable(main), "main function should be available"
