# src/schemas/__init__.py
import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).parent

def load_schema(schema_name: str) -> dict:
    """Load a JSON schema by name."""
    schema_file = SCHEMA_DIR / f"{schema_name}.json"
    if schema_file.exists():
        with open(schema_file, 'r') as f:
            return json.load(f)
    raise FileNotFoundError(f"Schema {schema_name} not found")

__all__ = ["load_schema"]