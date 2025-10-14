"""
Compatibility wrapper for Triton normalizer.
Provides TritonNormalizer expected by mef_core_pipeline.
"""
from typing import Any, Dict, Optional
from .triton_core import TritonCore

class TritonNormalizer:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.core = TritonCore(config or {"seed": "MEF_SEED_42"})

    def normalize(self, data: Any, data_type: str = "raw") -> Dict[str, Any]:
        return self.core.normalize(data, data_type)
