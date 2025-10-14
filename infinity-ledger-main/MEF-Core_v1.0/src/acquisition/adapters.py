"""
Acquisition adapters for MEF-Core.
Simple fallback adapter used by MEFCorePipeline.
"""
from typing import Any, Dict
import json

class AcquisitionAdapter:
    """Minimal adapter that wraps raw input into a structured dict."""
    def __init__(self, source: str = "generic"):
        self.source = source

    def collect(self, raw_input: Any, input_type: str) -> Dict[str, Any]:
        if input_type == "json" and isinstance(raw_input, str):
            data = json.loads(raw_input)
        elif input_type == "text" and isinstance(raw_input, str):
            data = {"text": raw_input.strip()}
        else:
            data = {"raw": raw_input, "type": input_type}
        return {"data": data, "metadata": {"source": self.source}}
