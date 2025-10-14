"""Enhanced logging utilities for benchmark and testing infrastructure.

This module provides structured logging with context, timing, and error tracking
to improve observability and debugging capabilities.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, TextIO


@dataclass
class LogContext:
    """Context information for structured logging."""
    
    component: str = "unknown"
    operation: str = ""
    request_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class StructuredLogger:
    """Structured logger with JSON output and timing capabilities."""
    
    def __init__(
        self,
        output: TextIO = sys.stderr,
        log_file: Optional[Path] = None,
        json_output: bool = False,
    ) -> None:
        """Initialize structured logger.
        
        Args:
            output: Output stream for logs (default: stderr)
            log_file: Optional file path for persistent logging
            json_output: Whether to output JSON format (default: False)
        """
        self.output = output
        self.log_file = log_file
        self.json_output = json_output
        self.context = LogContext()
        
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
    
    def set_context(
        self,
        component: Optional[str] = None,
        operation: Optional[str] = None,
        request_id: Optional[str] = None,
        **metadata: Any,
    ) -> None:
        """Set logging context for subsequent log entries.
        
        Args:
            component: Component name (e.g., 'bench_runner', 'compare')
            operation: Current operation (e.g., 'upsert', 'search')
            request_id: Unique request identifier
            **metadata: Additional metadata to include
        """
        if component is not None:
            self.context.component = component
        if operation is not None:
            self.context.operation = operation
        if request_id is not None:
            self.context.request_id = request_id
        if metadata:
            self.context.metadata.update(metadata)
    
    def _format_message(
        self,
        level: str,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Format log message based on output mode.
        
        Args:
            level: Log level (INFO, WARN, ERROR, etc.)
            message: Log message
            extra: Additional fields to include
            
        Returns:
            Formatted log string
        """
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        if self.json_output:
            entry: Dict[str, Any] = {
                "timestamp": timestamp,
                "level": level,
                "message": message,
                "component": self.context.component,
            }
            
            if self.context.operation:
                entry["operation"] = self.context.operation
            
            if self.context.request_id:
                entry["request_id"] = self.context.request_id
            
            if self.context.metadata:
                entry["metadata"] = self.context.metadata
            
            if extra:
                entry.update(extra)
            
            return json.dumps(entry)
        else:
            # Human-readable format
            parts = [f"[{timestamp}]", f"[{level}]"]
            
            if self.context.component:
                parts.append(f"[{self.context.component}]")
            
            if self.context.operation:
                parts.append(f"[{self.context.operation}]")
            
            parts.append(message)
            
            if extra:
                extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
                parts.append(f"({extra_str})")
            
            return " ".join(parts)
    
    def _write_log(self, formatted: str) -> None:
        """Write formatted log to outputs.
        
        Args:
            formatted: Formatted log string
        """
        print(formatted, file=self.output, flush=True)
        
        if self.log_file:
            try:
                with self.log_file.open("a", encoding="utf-8") as f:
                    f.write(formatted + "\n")
            except (OSError, IOError) as exc:
                # Don't fail if log file write fails
                print(
                    f"WARNING: Failed to write to log file: {exc}",
                    file=sys.stderr,
                )
    
    def info(self, message: str, **extra: Any) -> None:
        """Log informational message.
        
        Args:
            message: Log message
            **extra: Additional fields
        """
        formatted = self._format_message("INFO", message, extra or None)
        self._write_log(formatted)
    
    def warning(self, message: str, **extra: Any) -> None:
        """Log warning message.
        
        Args:
            message: Log message
            **extra: Additional fields
        """
        formatted = self._format_message("WARN", message, extra or None)
        self._write_log(formatted)
    
    def error(
        self,
        message: str,
        exc: Optional[Exception] = None,
        **extra: Any,
    ) -> None:
        """Log error message with optional exception details.
        
        Args:
            message: Log message
            exc: Optional exception to include
            **extra: Additional fields
        """
        if exc:
            extra = extra.copy() if extra else {}
            extra["error_type"] = type(exc).__name__
            extra["error_message"] = str(exc)
            
            if self.json_output:
                extra["traceback"] = traceback.format_exception(type(exc), exc, exc.__traceback__)
        
        formatted = self._format_message("ERROR", message, extra or None)
        self._write_log(formatted)
        
        # If not JSON mode and we have an exception, print traceback
        if exc and not self.json_output:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            print(tb, file=self.output)
    
    def debug(self, message: str, **extra: Any) -> None:
        """Log debug message.
        
        Args:
            message: Log message
            **extra: Additional fields
        """
        formatted = self._format_message("DEBUG", message, extra or None)
        self._write_log(formatted)
    
    @contextmanager
    def operation(self, operation: str, **metadata: Any):
        """Context manager for timing and logging operations.
        
        Args:
            operation: Operation name
            **metadata: Additional metadata
            
        Yields:
            Self for logging within context
            
        Example:
            with logger.operation("upsert", batch_size=1000):
                # do work
                logger.info("Processing batch")
        """
        old_operation = self.context.operation
        old_metadata = self.context.metadata.copy()
        
        self.set_context(operation=operation, **metadata)
        start_time = time.perf_counter()
        
        self.info(f"Starting operation: {operation}")
        
        try:
            yield self
        except Exception as exc:
            duration = time.perf_counter() - start_time
            self.error(
                f"Operation failed: {operation}",
                exc=exc,
                duration_seconds=round(duration, 3),
            )
            raise
        else:
            duration = time.perf_counter() - start_time
            self.info(
                f"Completed operation: {operation}",
                duration_seconds=round(duration, 3),
            )
        finally:
            self.context.operation = old_operation
            self.context.metadata = old_metadata
    
    @contextmanager
    def timer(self, label: str):
        """Context manager for timing code blocks.
        
        Args:
            label: Label for the timed block
            
        Yields:
            None
            
        Example:
            with logger.timer("Data preprocessing"):
                # do work
        """
        start_time = time.perf_counter()
        self.debug(f"Timer start: {label}")
        
        try:
            yield
        finally:
            duration = time.perf_counter() - start_time
            self.info(
                f"Timer: {label}",
                duration_seconds=round(duration, 3),
            )


def create_logger(
    component: str,
    log_dir: Optional[Path] = None,
    json_output: bool = False,
) -> StructuredLogger:
    """Create a configured structured logger.
    
    Args:
        component: Component name for the logger
        log_dir: Optional directory for log files
        json_output: Whether to use JSON output format
        
    Returns:
        Configured StructuredLogger instance
    """
    log_file = None
    if log_dir:
        log_file = log_dir / f"{component}.log"
    
    logger = StructuredLogger(
        output=sys.stderr,
        log_file=log_file,
        json_output=json_output,
    )
    logger.set_context(component=component)
    
    return logger


# Global logger instance for convenience
_default_logger: Optional[StructuredLogger] = None


def get_logger() -> StructuredLogger:
    """Get or create the default global logger.
    
    Returns:
        Global StructuredLogger instance
    """
    global _default_logger
    
    if _default_logger is None:
        _default_logger = StructuredLogger()
    
    return _default_logger


def set_default_logger(logger: Optional[StructuredLogger]) -> None:
    """Set the default global logger.
    
    Args:
        logger: StructuredLogger instance to use as default, or None to clear
    """
    global _default_logger
    _default_logger = logger
