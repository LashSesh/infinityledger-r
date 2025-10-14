from pathlib import Path

import pytest

from src.specs import BlueprintDocument, BlueprintSchemaError, BlueprintValidationError, load_blueprint


SPEC_PATH = Path(__file__).resolve().parent.parent / "specs" / "SPEC-002.yaml"


def test_loads_spec_002_successfully():
    document = load_blueprint(SPEC_PATH)

    assert isinstance(document, BlueprintDocument)
    assert document.model.spec.id == "SPEC-002"
    assert document.model.spec.title == "MEF-Core → Infinity Vector Ledger"
    assert document.model.priorities["must"]
    # The hash is stable because the serialization is deterministic.
    assert document.spec_hash == "cd9599687e716335701211554b46cd40acfca230c27cafdb97a563b0a620de27"


def test_invalid_blueprint_fails_schema(tmp_path: Path):
    invalid_blueprint = tmp_path / "invalid.yaml"
    invalid_blueprint.write_text(
        '{"spec": {"id": "SPEC-XYZ", "title": "Broken", "version": "0.0.1", "date": "2024-01-01"}}',
        encoding="utf-8",
    )

    with pytest.raises(BlueprintSchemaError):
        load_blueprint(invalid_blueprint)


def test_non_mapping_root(tmp_path: Path):
    invalid_blueprint = tmp_path / "list.yaml"
    invalid_blueprint.write_text("[{\"just\": \"a\", \"list\": \"value\"}]", encoding="utf-8")

    with pytest.raises(BlueprintValidationError):
        load_blueprint(invalid_blueprint)
