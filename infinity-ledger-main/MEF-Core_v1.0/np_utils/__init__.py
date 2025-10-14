"""Compatibility shim that prefers the real NumPy distribution.

This project historically shipped a lightweight in-repo ``numpy`` stub so the
quality suite could run without pulling the full dependency tree.  The recent
benchmarks, recall evaluation, and golden builders rely on functionality such
as ``numpy.savez``/``numpy.load`` that the stub never implemented, leading to
runtime errors inside CI where the real package *is* available.  To keep the
repository backwards compatible while restoring production correctness we now
attempt to import the vendor NumPy build from site-packages.  Only if it is
absent – or explicitly disabled via ``MEF_FORCE_STUB_NUMPY`` – do we fall back
to the legacy stub implementation.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import sysconfig
from pathlib import Path
from types import ModuleType
from typing import Iterable


def _candidate_roots() -> Iterable[Path]:
    """Yield plausible locations where a real NumPy install might live."""

    seen: set[Path] = set()
    config_paths = sysconfig.get_paths()
    for key in ("platlib", "purelib"):
        raw = config_paths.get(key)
        if not raw:
            continue
        path = Path(raw).resolve()
        if path not in seen:
            seen.add(path)
            yield path

    for entry in sys.path:
        try:
            resolved = Path(entry).resolve()
        except Exception:
            continue
        if resolved not in seen:
            seen.add(resolved)
            yield resolved


def _load_real_numpy() -> ModuleType | None:
    """Load the site-packages NumPy distribution if available."""

    current_file = Path(__file__).resolve()
    for root in _candidate_roots():
        candidate = root / "numpy" / "__init__.py"
        try:
            if not candidate.exists():
                continue
            if candidate.samefile(current_file):  # points back to this shim
                continue
        except FileNotFoundError:
            continue

        spec = importlib.util.spec_from_file_location(
            __name__,
            candidate,
            submodule_search_locations=[str(candidate.parent)],
        )
        if spec is None or spec.loader is None:
            continue

        module = importlib.util.module_from_spec(spec)
        # Replace the shim entry so relative imports inside NumPy resolve
        sys.modules[__name__] = module
        spec.loader.exec_module(module)
        return module

    return None


def _load_stub() -> ModuleType:
    """Import the historical in-repo stub as a last resort."""

    spec = importlib.util.spec_from_file_location(
        "_mef_numpy_stub",
        Path(__file__).with_name("_stub.py"),
    )
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load MEF numpy stub implementation")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if os.environ.get("MEF_FORCE_STUB_NUMPY", "").lower() in {"1", "true", "yes"}:
    _ACTIVE_MODULE = _load_stub()
else:
    _ACTIVE_MODULE = _load_real_numpy() or _load_stub()

# Re-export every public attribute from the selected implementation and update
# ``sys.modules`` so downstream ``import numpy`` statements keep working.
globals().update({name: getattr(_ACTIVE_MODULE, name) for name in dir(_ACTIVE_MODULE)})
__all__ = getattr(
    _ACTIVE_MODULE,
    "__all__",
    [name for name in globals() if not name.startswith("_")],
)
sys.modules[__name__] = _ACTIVE_MODULE

