# src/audit/__init__.py
from .logger import MEFAuditLogger

__all__ = ["MEFAuditLogger"]

def main():
    """Main entry point for audit logger."""
    logger = MEFAuditLogger()
    print(f"Audit logger initialized: {logger.log_file}")