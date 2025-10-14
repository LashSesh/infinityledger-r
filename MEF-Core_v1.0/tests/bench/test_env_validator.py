"""Tests for environment variable validation utilities."""

from __future__ import annotations

import os
import pytest

from tests.bench.env_validator import (
    EnvValidationError,
    validate_positive_int,
    validate_positive_float,
    validate_url,
    validate_bool,
    validate_comma_list,
)


class TestValidatePositiveInt:
    """Tests for validate_positive_int function."""
    
    def test_uses_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = validate_positive_int("TEST_VAR", default=100)
        assert result == 100
    
    def test_parses_valid_integer(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "42")
        result = validate_positive_int("TEST_VAR", default=100)
        assert result == 42
    
    def test_enforces_min_value(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "5")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_int("TEST_VAR", default=100, min_value=10)
        assert "must be >= 10" in str(exc_info.value)
    
    def test_enforces_max_value(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "150")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_int("TEST_VAR", default=100, max_value=100)
        assert "must be <= 100" in str(exc_info.value)
    
    def test_rejects_non_integer(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "not_a_number")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_int("TEST_VAR", default=100)
        assert "must be an integer" in str(exc_info.value)
    
    def test_handles_empty_string(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "   ")
        result = validate_positive_int("TEST_VAR", default=100)
        assert result == 100


class TestValidatePositiveFloat:
    """Tests for validate_positive_float function."""
    
    def test_uses_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = validate_positive_float("TEST_VAR", default=1.5)
        assert result == 1.5
    
    def test_parses_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "3.14")
        result = validate_positive_float("TEST_VAR", default=1.5)
        assert result == 3.14
    
    def test_parses_integer_as_float(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "42")
        result = validate_positive_float("TEST_VAR", default=1.5)
        assert result == 42.0
    
    def test_enforces_min_value(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "0.5")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_float("TEST_VAR", default=1.5, min_value=1.0)
        assert "must be >= 1.0" in str(exc_info.value)
    
    def test_enforces_max_value(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "10.0")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_float("TEST_VAR", default=1.5, max_value=5.0)
        assert "must be <= 5.0" in str(exc_info.value)
    
    def test_rejects_non_numeric(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "not_a_number")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_positive_float("TEST_VAR", default=1.5)
        assert "must be a number" in str(exc_info.value)


class TestValidateUrl:
    """Tests for validate_url function."""
    
    def test_uses_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = validate_url("TEST_VAR", default="http://localhost:8080")
        assert result == "http://localhost:8080"
    
    def test_parses_valid_url(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "http://api:8080")
        result = validate_url("TEST_VAR", default="http://localhost:8080")
        assert result == "http://api:8080"
    
    def test_removes_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "http://api:8080/")
        result = validate_url("TEST_VAR", default="http://localhost:8080")
        assert result == "http://api:8080"
    
    def test_validates_scheme(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "ftp://api:8080")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_url("TEST_VAR", default="http://localhost:8080", schemes=["http", "https"])
        assert "scheme must be one of" in str(exc_info.value)
    
    def test_rejects_missing_scheme(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "localhost:8080")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_url("TEST_VAR", default="http://localhost:8080")
        assert "missing scheme" in str(exc_info.value)
    
    def test_rejects_empty_url(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "")
        monkeypatch.delenv("TEST_VAR")
        # Default cannot be empty
        with pytest.raises(EnvValidationError) as exc_info:
            validate_url("TEST_VAR", default="")
        assert "cannot be empty" in str(exc_info.value)


class TestValidateBool:
    """Tests for validate_bool function."""
    
    def test_uses_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = validate_bool("TEST_VAR", default=True)
        assert result is True
    
    @pytest.mark.parametrize("value", ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON"])
    def test_parses_true_values(self, monkeypatch, value):
        monkeypatch.setenv("TEST_VAR", value)
        result = validate_bool("TEST_VAR", default=False)
        assert result is True
    
    @pytest.mark.parametrize("value", ["false", "FALSE", "False", "0", "no", "NO", "off", "OFF"])
    def test_parses_false_values(self, monkeypatch, value):
        monkeypatch.setenv("TEST_VAR", value)
        result = validate_bool("TEST_VAR", default=True)
        assert result is False
    
    def test_rejects_invalid_bool(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "maybe")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_bool("TEST_VAR", default=False)
        assert "must be boolean" in str(exc_info.value)


class TestValidateCommaList:
    """Tests for validate_comma_list function."""
    
    def test_uses_default_when_not_set(self, monkeypatch):
        monkeypatch.delenv("TEST_VAR", raising=False)
        result = validate_comma_list("TEST_VAR", default=["a", "b"])
        assert result == ["a", "b"]
    
    def test_parses_comma_separated_list(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "mef,faiss,qdrant")
        result = validate_comma_list("TEST_VAR", default=[])
        assert result == ["mef", "faiss", "qdrant"]
    
    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", " mef , faiss , qdrant ")
        result = validate_comma_list("TEST_VAR", default=[])
        assert result == ["mef", "faiss", "qdrant"]
    
    def test_validates_allowed_values(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "mef,invalid,qdrant")
        with pytest.raises(EnvValidationError) as exc_info:
            validate_comma_list("TEST_VAR", default=[], allowed_values=["mef", "faiss", "qdrant"])
        assert "invalid values" in str(exc_info.value)
    
    def test_handles_empty_string(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "")
        result = validate_comma_list("TEST_VAR", default=["default"])
        assert result == ["default"]
    
    def test_ignores_empty_tokens(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "mef,,qdrant,")
        result = validate_comma_list("TEST_VAR", default=[])
        assert result == ["mef", "qdrant"]


class TestEnvValidationError:
    """Tests for EnvValidationError exception."""
    
    def test_stores_variable_name(self):
        error = EnvValidationError("TEST_VAR", "some reason")
        assert error.variable == "TEST_VAR"
    
    def test_stores_reason(self):
        error = EnvValidationError("TEST_VAR", "some reason")
        assert error.reason == "some reason"
    
    def test_message_format(self):
        error = EnvValidationError("TEST_VAR", "some reason")
        assert "TEST_VAR" in str(error)
        assert "some reason" in str(error)
