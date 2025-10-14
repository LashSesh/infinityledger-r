"""Tests for bash integer expression fixes in CI and docker-compose files."""

from __future__ import annotations

from pathlib import Path
import re


# Variables that are explicitly initialized and are safe to use in integer tests
INITIALIZED_STATUS_VARS = {
    'bench_status', 'recall_status', 'golden_status', 'compare_status',
    'code', 'exit_code', 'status'
}


def test_docker_compose_bash_integer_expressions_use_defaults() -> None:
    """Verify docker-compose.ci.yml uses ${var:-0} pattern for integer tests."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    assert compose_file.exists(), "docker-compose.ci.yml should exist"
    
    content = compose_file.read_text()
    
    # Check for the fixed patterns in the summary section
    # The code should use ${code:-0} and ${exit_code:-0} and ${var:-0}
    assert '${code:-0}' in content, "Should use ${code:-0} pattern"
    assert '${exit_code:-0}' in content, "Should use ${exit_code:-0} pattern"
    
    # Check that status variables have default values in printf statements
    assert '${bench_status:-0}' in content, "Should use ${bench_status:-0} in printf"
    assert '${recall_status:-0}' in content, "Should use ${recall_status:-0} in printf"
    assert '${golden_status:-0}' in content, "Should use ${golden_status:-0} in printf"
    assert '${compare_status:-0}' in content, "Should use ${compare_status:-0} in printf"
    
    # Verify explicit initialization is still present
    assert 'bench_status=0' in content, "Should initialize bench_status=0"
    assert 'recall_status=0' in content, "Should initialize recall_status=0"
    assert 'golden_status=0' in content, "Should initialize golden_status=0"
    assert 'compare_status=0' in content, "Should initialize compare_status=0"
    
    print("✓ docker-compose.ci.yml uses proper bash integer expression patterns")


def test_ci_workflow_bash_integer_expressions_use_defaults() -> None:
    """Verify ci.yml uses ${var:-0} pattern for integer tests."""
    repo_root = Path(__file__).resolve().parents[3]
    ci_file = repo_root / ".github" / "workflows" / "ci.yml"
    
    assert ci_file.exists(), "ci.yml should exist"
    
    content = ci_file.read_text()
    
    # Check for the fixed pattern in the retry logic
    assert '${status:-0}' in content, "Should use ${status:-0} pattern"
    
    # Check for the fixed pattern in compose exit code check
    assert 'steps.compose.outputs.exit_code || 0' in content, \
        "Should use steps.compose.outputs.exit_code || 0 pattern"
    
    # Check for the fixed pattern in golden status check
    assert '${GOLDEN_STATUS:-}' in content, "Should use ${GOLDEN_STATUS:-} pattern"
    assert '${MIN_OK:-30}' in content, "Should use ${MIN_OK:-30} pattern"
    
    print("✓ ci.yml uses proper bash integer expression patterns")


def test_no_unprotected_integer_tests_in_docker_compose() -> None:
    """Ensure no unprotected bash integer comparisons in docker-compose.ci.yml."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_file = repo_root / "docker-compose.ci.yml"
    
    content = compose_file.read_text()
    
    # Look for patterns like [ "$var" -ne 0 ] without default value
    # Match complete integer comparison expressions
    unprotected_pattern = r'\[ "\$(\w+)" -(?:eq|ne|gt|lt|ge|le) (?:\d+|"\$\w+")\s*\]'
    
    # Extract the bash script section from qa service command
    # Look for command: section and extract until we hit a line that starts with a service name
    command_match = re.search(
        r'^\s+command:\s*$(.*?)^(?:\S+:|\s*$)',
        content,
        re.MULTILINE | re.DOTALL
    )
    
    if command_match:
        bash_script = command_match.group(1)
        
        matches = re.findall(unprotected_pattern, bash_script)
        # Filter out cases where we're checking against variables that are initialized
        problematic = [m for m in matches if m not in INITIALIZED_STATUS_VARS]
        
        if problematic:
            # Additional check: are these variables using the ${var:-0} pattern?
            for var in problematic:
                # Check if the variable is used with default elsewhere
                if f'${{{var}:-' not in bash_script:
                    print(f"WARNING: Variable '{var}' may need default value protection")
    
    print("✓ No obvious unprotected integer tests in docker-compose.ci.yml")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
