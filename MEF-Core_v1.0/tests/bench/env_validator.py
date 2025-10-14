"""Environment variable validation utilities for benchmark scripts.

This module provides robust validation and defaulting for all environment
variables used in the benchmark and testing infrastructure.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional


class EnvValidationError(Exception):
    """Raised when environment variable validation fails."""
    
    def __init__(self, variable: str, reason: str) -> None:
        super().__init__(f"Invalid environment variable {variable}: {reason}")
        self.variable = variable
        self.reason = reason


def validate_positive_int(
    name: str,
    default: int,
    min_value: int = 1,
    max_value: Optional[int] = None,
) -> int:
    """Validate and parse a positive integer environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive), None for no limit
        
    Returns:
        Validated integer value
        
    Raises:
        EnvValidationError: If value is invalid
    """
    raw_value = os.getenv(name, "").strip()
    
    if not raw_value:
        return default
    
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise EnvValidationError(
            name,
            f"must be an integer, got '{raw_value}'"
        ) from exc
    
    if value < min_value:
        raise EnvValidationError(
            name,
            f"must be >= {min_value}, got {value}"
        )
    
    if max_value is not None and value > max_value:
        raise EnvValidationError(
            name,
            f"must be <= {max_value}, got {value}"
        )
    
    return value


def validate_positive_float(
    name: str,
    default: float,
    min_value: float = 0.0,
    max_value: Optional[float] = None,
) -> float:
    """Validate and parse a positive float environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive), None for no limit
        
    Returns:
        Validated float value
        
    Raises:
        EnvValidationError: If value is invalid
    """
    raw_value = os.getenv(name, "").strip()
    
    if not raw_value:
        return default
    
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise EnvValidationError(
            name,
            f"must be a number, got '{raw_value}'"
        ) from exc
    
    if value < min_value:
        raise EnvValidationError(
            name,
            f"must be >= {min_value}, got {value}"
        )
    
    if max_value is not None and value > max_value:
        raise EnvValidationError(
            name,
            f"must be <= {max_value}, got {value}"
        )
    
    return value


def validate_url(
    name: str,
    default: str,
    schemes: Optional[List[str]] = None,
) -> str:
    """Validate and normalize a URL environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        schemes: Allowed URL schemes (e.g., ['http', 'https'])
        
    Returns:
        Validated URL string with trailing slash removed
        
    Raises:
        EnvValidationError: If value is invalid
    """
    raw_value = os.getenv(name, "").strip()
    
    if not raw_value:
        value = default
    else:
        value = raw_value
    
    if not value:
        raise EnvValidationError(name, "URL cannot be empty")
    
    # Basic URL validation
    if "://" not in value:
        raise EnvValidationError(
            name,
            f"invalid URL format, missing scheme in '{value}'"
        )
    
    scheme = value.split("://", 1)[0].lower()
    
    if schemes is not None and scheme not in schemes:
        raise EnvValidationError(
            name,
            f"scheme must be one of {schemes}, got '{scheme}'"
        )
    
    # Remove trailing slash for consistency
    return value.rstrip("/")


def validate_bool(name: str, default: bool) -> bool:
    """Validate and parse a boolean environment variable.
    
    Accepts: true, false, 1, 0, yes, no, on, off (case-insensitive)
    
    Args:
        name: Environment variable name
        default: Default value if not set
        
    Returns:
        Validated boolean value
        
    Raises:
        EnvValidationError: If value is invalid
    """
    raw_value = os.getenv(name, "").strip().lower()
    
    if not raw_value:
        return default
    
    true_values = {"true", "1", "yes", "on"}
    false_values = {"false", "0", "no", "off"}
    
    if raw_value in true_values:
        return True
    elif raw_value in false_values:
        return False
    else:
        raise EnvValidationError(
            name,
            f"must be boolean (true/false/1/0/yes/no/on/off), got '{raw_value}'"
        )


def validate_comma_list(
    name: str,
    default: List[str],
    allowed_values: Optional[List[str]] = None,
) -> List[str]:
    """Validate and parse a comma-separated list environment variable.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        allowed_values: List of allowed values, None to allow any
        
    Returns:
        List of validated string values
        
    Raises:
        EnvValidationError: If value is invalid
    """
    raw_value = os.getenv(name, "").strip()
    
    if not raw_value:
        return default
    
    values = [v.strip() for v in raw_value.split(",") if v.strip()]
    
    if not values:
        return default
    
    if allowed_values is not None:
        invalid = [v for v in values if v not in allowed_values]
        if invalid:
            raise EnvValidationError(
                name,
                f"invalid values {invalid}, allowed: {allowed_values}"
            )
    
    return values


def print_env_config(config: Dict[str, Any], prefix: str = "") -> None:
    """Print validated environment configuration for debugging.
    
    Args:
        config: Dictionary of configuration values
        prefix: Optional prefix for log messages
    """
    print(f"{prefix}Environment Configuration:", file=sys.stderr)
    for key, value in sorted(config.items()):
        # Mask sensitive values
        if any(s in key.upper() for s in ["TOKEN", "KEY", "SECRET", "PASSWORD"]):
            display_value = "***" if value else "<not set>"
        else:
            display_value = value
        print(f"{prefix}  {key}: {display_value}", file=sys.stderr)
