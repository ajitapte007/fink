"""Structured logging configuration."""

import logging
import sys
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    """JSON-ish structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        level = record.levelname
        name = record.name
        msg = record.getMessage()
        extra = ""
        if hasattr(record, "extra_data"):
            extra = f" | {record.extra_data}"
        return f"[{ts}] {level:8s} | {name} | {msg}{extra}"


def setup_logging(level: str = "INFO") -> None:
    """Configure application-wide logging."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger("gepa")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = [handler]
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"gepa.{name}")
