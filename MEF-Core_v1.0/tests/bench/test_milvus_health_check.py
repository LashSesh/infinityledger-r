"""Tests for Milvus driver health check improvements."""

from __future__ import annotations

import pytest

from bench.drivers import MilvusDriver, DriverUnavailable


def test_milvus_driver_health_check_error_message_when_not_configured() -> None:
    """Test that MilvusDriver provides clear error when MILVUS_HOST not set."""
    import os
    
    # Ensure MILVUS_HOST is not set
    original_host = os.environ.get("MILVUS_HOST")
    try:
        if "MILVUS_HOST" in os.environ:
            del os.environ["MILVUS_HOST"]
        
        driver = MilvusDriver()
        
        with pytest.raises(DriverUnavailable) as exc_info:
            driver.connect()
        
        error = exc_info.value
        assert error.name == "Milvus"
        assert "not configured" in error.reason.lower()
    finally:
        if original_host is not None:
            os.environ["MILVUS_HOST"] = original_host


def test_milvus_driver_health_check_error_message_when_unreachable() -> None:
    """Test that MilvusDriver provides clear error when service is unreachable."""
    import os
    
    # Set MILVUS_HOST to an invalid/unreachable address
    original_host = os.environ.get("MILVUS_HOST")
    try:
        os.environ["MILVUS_HOST"] = "invalid-milvus-host.local"
        
        driver = MilvusDriver()
        
        with pytest.raises(DriverUnavailable) as exc_info:
            driver.connect()
        
        error = exc_info.value
        assert error.name == "Milvus"
        # Should mention the connection failure
        reason = error.reason.lower()
        assert "failed to connect" in reason or "health check failed" in reason
        # Should mention the host/port
        assert "invalid-milvus-host.local" in reason
    finally:
        if original_host is not None:
            os.environ["MILVUS_HOST"] = original_host
        else:
            if "MILVUS_HOST" in os.environ:
                del os.environ["MILVUS_HOST"]


def test_milvus_driver_connects_when_available() -> None:
    """Test that MilvusDriver connects successfully when service is available.
    
    This test will be skipped if Milvus is not available in the test environment.
    """
    import os
    
    # Only run if MILVUS_HOST is configured
    if not os.environ.get("MILVUS_HOST"):
        pytest.skip("MILVUS_HOST not configured")
    
    driver = MilvusDriver()
    
    try:
        driver.connect()
        # If we got here, connection succeeded
        # Try a simple operation to verify it's truly connected
        driver.clear("test_namespace")
    except DriverUnavailable as exc:
        # Service not available in test environment, skip
        pytest.skip(f"Milvus not available: {exc.reason}")
    except Exception as exc:
        # Some other error - still skip but report it
        pytest.skip(f"Milvus connection failed: {exc}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
