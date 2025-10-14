"""Tests for structured logging utilities."""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

import pytest

from tests.bench.logger import (
    LogContext,
    StructuredLogger,
    create_logger,
    get_logger,
    set_default_logger,
)


class TestLogContext:
    """Tests for LogContext dataclass."""
    
    def test_default_values(self):
        ctx = LogContext()
        assert ctx.component == "unknown"
        assert ctx.operation == ""
        assert ctx.request_id is None
        assert ctx.metadata == {}
    
    def test_custom_values(self):
        ctx = LogContext(
            component="test_component",
            operation="test_op",
            request_id="req-123",
            metadata={"key": "value"},
        )
        assert ctx.component == "test_component"
        assert ctx.operation == "test_op"
        assert ctx.request_id == "req-123"
        assert ctx.metadata == {"key": "value"}


class TestStructuredLogger:
    """Tests for StructuredLogger class."""
    
    def test_initialization_defaults(self):
        logger = StructuredLogger()
        assert logger.json_output is False
        assert logger.log_file is None
        assert logger.context.component == "unknown"
    
    def test_set_context(self):
        logger = StructuredLogger()
        logger.set_context(
            component="my_component",
            operation="my_operation",
            request_id="req-456",
            custom_key="custom_value",
        )
        
        assert logger.context.component == "my_component"
        assert logger.context.operation == "my_operation"
        assert logger.context.request_id == "req-456"
        assert logger.context.metadata["custom_key"] == "custom_value"
    
    def test_info_logging_human_readable(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        logger.set_context(component="test")
        
        logger.info("Test message")
        
        result = output.getvalue()
        assert "[INFO]" in result
        assert "[test]" in result
        assert "Test message" in result
    
    def test_info_logging_json(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        logger.set_context(component="test")
        
        logger.info("Test message")
        
        result = output.getvalue().strip()
        data = json.loads(result)
        
        assert data["level"] == "INFO"
        assert data["message"] == "Test message"
        assert data["component"] == "test"
        assert "timestamp" in data
    
    def test_warning_logging(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        
        logger.warning("Warning message")
        
        result = output.getvalue()
        assert "[WARN]" in result
        assert "Warning message" in result
    
    def test_error_logging_with_exception(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        
        try:
            raise ValueError("Test error")
        except ValueError as exc:
            logger.error("Error occurred", exc=exc)
        
        result = output.getvalue().strip()
        data = json.loads(result)
        
        assert data["level"] == "ERROR"
        assert data["message"] == "Error occurred"
        assert data["error_type"] == "ValueError"
        assert data["error_message"] == "Test error"
        assert "traceback" in data
    
    def test_debug_logging(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        
        logger.debug("Debug message", extra_field="extra_value")
        
        result = output.getvalue()
        assert "[DEBUG]" in result
        assert "Debug message" in result
    
    def test_logging_with_extra_fields(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        
        logger.info("Message", user_id=123, action="create")
        
        result = output.getvalue().strip()
        data = json.loads(result)
        
        assert data["user_id"] == 123
        assert data["action"] == "create"
    
    def test_operation_context_manager_success(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        
        with logger.operation("test_operation", batch_size=100):
            pass
        
        lines = output.getvalue().strip().split("\n")
        assert len(lines) == 2  # Start and completion messages
        
        start_data = json.loads(lines[0])
        end_data = json.loads(lines[1])
        
        assert "Starting operation: test_operation" in start_data["message"]
        assert "Completed operation: test_operation" in end_data["message"]
        assert "duration_seconds" in end_data
    
    def test_operation_context_manager_failure(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        
        with pytest.raises(RuntimeError):
            with logger.operation("failing_operation"):
                raise RuntimeError("Test failure")
        
        lines = output.getvalue().strip().split("\n")
        error_data = json.loads(lines[-1])
        
        assert error_data["level"] == "ERROR"
        assert "Operation failed: failing_operation" in error_data["message"]
        assert error_data["error_type"] == "RuntimeError"
        assert "duration_seconds" in error_data
    
    def test_timer_context_manager(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        
        with logger.timer("test_block"):
            pass
        
        lines = output.getvalue().strip().split("\n")
        # Should have debug start and info completion
        assert len(lines) >= 2
        
        timer_data = json.loads(lines[-1])
        assert "Timer: test_block" in timer_data["message"]
        assert "duration_seconds" in timer_data
    
    def test_log_file_writing(self, tmp_path):
        log_file = tmp_path / "test.log"
        logger = StructuredLogger(log_file=log_file, json_output=False)
        
        logger.info("Test message to file")
        
        assert log_file.exists()
        content = log_file.read_text()
        assert "[INFO]" in content
        assert "Test message to file" in content
    
    def test_context_restoration_after_operation(self):
        logger = StructuredLogger()
        logger.set_context(operation="original_op", key1="value1")
        
        with logger.operation("nested_op", key2="value2"):
            assert logger.context.operation == "nested_op"
            assert "key2" in logger.context.metadata
        
        # Context should be restored
        assert logger.context.operation == "original_op"
        assert "key1" in logger.context.metadata
        assert "key2" not in logger.context.metadata


class TestLoggerFactory:
    """Tests for logger factory functions."""
    
    def test_create_logger_basic(self):
        logger = create_logger("my_component")
        assert logger.context.component == "my_component"
        assert logger.log_file is None
    
    def test_create_logger_with_log_dir(self, tmp_path):
        logger = create_logger("my_component", log_dir=tmp_path)
        assert logger.log_file == tmp_path / "my_component.log"
    
    def test_create_logger_with_json_output(self):
        logger = create_logger("my_component", json_output=True)
        assert logger.json_output is True
    
    def test_get_logger_creates_default(self):
        # Clear any existing default
        set_default_logger(None)
        
        logger = get_logger()
        assert isinstance(logger, StructuredLogger)
    
    def test_set_and_get_default_logger(self):
        custom_logger = StructuredLogger()
        custom_logger.set_context(component="custom")
        
        set_default_logger(custom_logger)
        retrieved = get_logger()
        
        assert retrieved is custom_logger
        assert retrieved.context.component == "custom"


class TestLogFormatting:
    """Tests for log message formatting."""
    
    def test_human_readable_format_basic(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        logger.set_context(component="formatter_test")
        
        logger.info("Basic message")
        
        result = output.getvalue()
        # Should contain timestamp, level, component, and message
        assert "[INFO]" in result
        assert "[formatter_test]" in result
        assert "Basic message" in result
        # Timestamp format check
        assert result.count("[") >= 3  # [timestamp], [INFO], [component]
    
    def test_human_readable_format_with_operation(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        logger.set_context(component="test", operation="search")
        
        logger.info("Operation message")
        
        result = output.getvalue()
        assert "[search]" in result
    
    def test_json_format_completeness(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=True)
        logger.set_context(
            component="json_test",
            operation="validate",
            request_id="req-789",
            env="test",
        )
        
        logger.info("JSON message", status="success")
        
        data = json.loads(output.getvalue().strip())
        
        # Check all expected fields
        assert data["timestamp"]
        assert data["level"] == "INFO"
        assert data["message"] == "JSON message"
        assert data["component"] == "json_test"
        assert data["operation"] == "validate"
        assert data["request_id"] == "req-789"
        assert data["metadata"]["env"] == "test"
        assert data["status"] == "success"


class TestErrorHandling:
    """Tests for error handling in logging."""
    
    def test_log_file_write_failure_does_not_crash(self, tmp_path):
        # Create read-only directory
        log_dir = tmp_path / "readonly"
        log_dir.mkdir()
        log_dir.chmod(0o444)
        
        log_file = log_dir / "test.log"
        output = StringIO()
        logger = StructuredLogger(output=output, log_file=log_file)
        
        # Should not raise exception
        logger.info("Test message")
        
        # Check that message still went to output stream
        assert "Test message" in output.getvalue()
    
    def test_exception_without_traceback_in_human_mode(self):
        output = StringIO()
        logger = StructuredLogger(output=output, json_output=False)
        
        try:
            raise ValueError("Test")
        except ValueError as exc:
            logger.error("Error", exc=exc)
        
        result = output.getvalue()
        assert "[ERROR]" in result
        assert "ValueError" in result
        # Traceback should be printed separately
        assert "Traceback" in result or "ValueError: Test" in result
