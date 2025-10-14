"""Test-wide fixtures and deterministic seeding helpers."""

import os
import random

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore

SEED = int(os.getenv("GOLDEN_SEED", "1337"))

random.seed(SEED)
if np is not None and hasattr(np, "random"):
    try:  # pragma: no cover - optional dependency
        np.random.seed(SEED)
    except Exception:  # pragma: no cover
        pass

