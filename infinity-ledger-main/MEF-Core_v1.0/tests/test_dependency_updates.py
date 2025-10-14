"""Test that dependency updates are correct and compatible."""

from pathlib import Path


def test_pymilvus_version_updated() -> None:
    """Verify pymilvus has been updated to 2.5.0."""
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    
    with open(requirements_file) as f:
        requirements = f.read()
    
    # Should have pymilvus 2.5.0
    assert "pymilvus==2.5.0" in requirements, \
        "pymilvus should be version 2.5.0"
    
    # Should NOT have the old version
    assert "pymilvus==2.4.4" not in requirements, \
        "pymilvus 2.4.4 should be replaced"
    
    print("✓ pymilvus correctly updated to 2.5.0")


def test_marshmallow_constraint_added() -> None:
    """Verify marshmallow constraint has been added."""
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    
    with open(requirements_file) as f:
        requirements = f.read()
    
    # Should have marshmallow with minimum version
    assert "marshmallow>=3.13.0" in requirements, \
        "marshmallow>=3.13.0 constraint should be present"
    
    print("✓ marshmallow constraint correctly added")


def test_all_required_dependencies_present() -> None:
    """Verify all required dependencies are in requirements.txt."""
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    
    with open(requirements_file) as f:
        requirements = f.read()
    
    required_packages = [
        "pymilvus",
        "qdrant-client",
        "faiss-cpu",
        "marshmallow",
        "numpy",
        "grpcio",
    ]
    
    for package in required_packages:
        assert package in requirements, \
            f"{package} must be in requirements.txt"
    
    print("✓ All required dependencies present")


def test_requirements_file_syntax() -> None:
    """Verify requirements.txt has valid syntax."""
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    
    with open(requirements_file) as f:
        lines = f.readlines()
    
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        
        # Should have package name
        assert line[0].isalpha() or line[0].isdigit(), \
            f"Line {i} has invalid syntax: {line}"
        
        # Should have version specifier
        has_version = any(op in line for op in ["==", ">=", "<=", ">", "<", "~="])
        assert has_version, \
            f"Line {i} should have version specifier: {line}"
    
    print("✓ requirements.txt syntax is valid")


def test_no_environs_dependency() -> None:
    """Verify environs is not in requirements (it was causing the issue)."""
    requirements_file = Path(__file__).resolve().parents[1] / "requirements.txt"
    
    with open(requirements_file) as f:
        requirements = f.read()
    
    # environs should NOT be explicitly listed
    # (pymilvus 2.5.0 doesn't need it)
    assert "environs" not in requirements.lower(), \
        "environs should not be in requirements.txt"
    
    print("✓ No environs dependency (correctly removed by pymilvus 2.5.0)")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
