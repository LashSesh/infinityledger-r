"""Cross-DB compare benchmark helpers."""

# Import the main() function from the sibling compare.py module
# We need to do this carefully because of the naming conflict between
# the compare.py file and the compare/ package directory
import importlib.util
import sys
from pathlib import Path

_parent_dir = Path(__file__).resolve().parent.parent
_compare_py_path = _parent_dir / "compare.py"

# Try to load and re-export main() and _connect_with_retries from compare.py
# If loading fails, we still need to provide a main() function that can write error reports
_load_error: Exception | None = None

if not _compare_py_path.exists():
    _load_error = FileNotFoundError(f"compare.py not found at {_compare_py_path}")
elif _compare_py_path.exists():
    try:
        spec = importlib.util.spec_from_file_location("_compare_module", _compare_py_path)
        if spec and spec.loader:
            _compare_module = importlib.util.module_from_spec(spec)
            # Register module in sys.modules before exec_module to avoid AttributeError
            # in Python 3.11 when @dataclass decorator tries to look up the module
            sys.modules[spec.name] = _compare_module
            try:
                spec.loader.exec_module(_compare_module)
            except Exception:
                # Clean up sys.modules if exec_module fails (mimics standard import behavior)
                # We catch all exceptions here because we want to clean up regardless of failure type
                # (ImportError, SyntaxError, RuntimeError, AttributeError, etc.)
                # The exception is re-raised and handled by the outer try/except block
                sys.modules.pop(spec.name, None)
                raise
            # Re-export the functions
            main = _compare_module.main
            _connect_with_retries = _compare_module._connect_with_retries
            __all__ = ["main", "_connect_with_retries"]
        else:
            _load_error = ImportError(f"Could not create module spec for {_compare_py_path}")
    except Exception as exc:
        _load_error = exc

if _load_error is not None:
    # If we couldn't load compare.py, provide a stub main() that reports the error
    def main() -> int:
        """Fallback main() that reports the import error."""
        import json
        import traceback
        from datetime import datetime
        
        error_msg = str(_load_error) or _load_error.__class__.__name__
        stack = "".join(traceback.format_exception(_load_error)).strip()
        
        # REPO_ROOT is 2 levels up from _parent_dir (tests/bench)
        repo_root = _parent_dir.parent.parent
        assets_dir = repo_root / "assets" / "bench"
        assets_dir.mkdir(parents=True, exist_ok=True)
        
        json_report = assets_dir / "compare.json"
        md_report = assets_dir / "compare.md"
        
        # Write JSON report
        payload = {
            "status": "error",
            "error": f"Failed to import compare module: {error_msg}",
            "traceback": stack,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "targets": [],
        }
        json_report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        
        # Write markdown report
        lines = [
            "# Vector Store Compare Benchmark",
            "",
            "## Error",
            "",
            f"Failed to import compare module: {error_msg}",
            "",
            "```",
            stack,
            "```",
        ]
        md_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        
        print(json.dumps(payload), file=sys.stderr)
        return 1
    
    # Provide a stub for _connect_with_retries
    def _connect_with_retries(*args, **kwargs):  # type: ignore
        """Fallback _connect_with_retries that raises the import error."""
        raise _load_error
    
    __all__ = ["main", "_connect_with_retries"]

