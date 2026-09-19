"""Structured logging. Log stages and timings, never API keys or raw audio."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with any ``extra=`` fields merged in."""

    _standard_fields = set(logging.makeLogRecord({}).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(
            (key, value)
            for key, value in record.__dict__.items()
            if key not in self._standard_fields and not key.startswith("_")
        )
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable: ``12:01:05 INFO  brain turn_routed speaker=Rahul bots=['dost']``."""

    def format(self, record: logging.LogRecord) -> str:
        fields = " ".join(
            f"{key}={value}"
            for key, value in record.__dict__.items()
            if key not in JsonFormatter._standard_fields and not key.startswith("_")
        )
        time = self.formatTime(record, "%H:%M:%S")
        line = f"{time} {record.levelname:<5} {record.name} {record.getMessage()} {fields}"
        return line.rstrip()


def configure_logging(*, level: str = "INFO", log_format: str = "json") -> None:
    # Windows defaults to a cp1252 console encoding, which turns Hindi into "\u0939" escapes.
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name if name.startswith("roxstar") else f"roxstar.{name}")
