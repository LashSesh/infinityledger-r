"""Compat helpers for NumPy dtype access across minimal builds."""

from __future__ import annotations

import numpy as np


def dtype_type(name: str, fallback):
    """Return the dtype type for *name* with a graceful fallback."""
    attr = getattr(np, name, None)
    if attr is not None:
        return attr
    try:
        return np.dtype(name).type
    except (TypeError, ValueError, AttributeError):
        return fallback


F32 = dtype_type("float32", float)
U32 = dtype_type("uint32", int)
