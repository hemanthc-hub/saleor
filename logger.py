"""
logger.py — HegmaKart structured logging module

Environment-aware Loguru configuration:
  - DEBUG=True  (local dev): colored stdout  +  rotating file  logs/flask_app.log
  - DEBUG=False (production): single-line JSON streamed to stdout only
                              (captured by AWS awslogs Docker driver → CloudWatch)

Usage
-----
    from logger import get_logger
    log = get_logger()
    log.info("event description", event="my_event", user_identifier=mobile)

Correlation IDs are injected automatically via the ContextVar set in api.py
before_request middleware — no extra work needed at call sites.
"""

import os
import sys
import json
from contextvars import ContextVar
from datetime import datetime, timezone

from loguru import logger

# ── ContextVar that holds the correlation ID for the current request ──────────
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")


def set_correlation_id(cid: str) -> None:
    """Called from the Flask before_request hook."""
    _correlation_id.set(cid)


def get_correlation_id() -> str:
    return _correlation_id.get()


# ── Formatters ────────────────────────────────────────────────────────────────

def _local_format(record: dict) -> str:
    """
    Human-readable format for local development.
    Example:
      2026-06-15T00:12:34.567Z | INFO     | api:sendOtp:89 | OTP sent | cid=req-abc
    """
    ts = datetime.fromtimestamp(record["time"].timestamp(), tz=timezone.utc)
    iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"
    cid = _correlation_id.get()
    level = record["level"].name
    name = record["name"]
    func = record["function"]
    line = record["line"]
    msg = record["message"]

    # Extra context fields appended after the message
    extra = record.get("extra", {})
    extra_str = "  ".join(f"{k}={v}" for k, v in extra.items() if k != "correlation_id")

    base = f"{iso_ts} | {level:<8} | {name}:{func}:{line} | cid={cid} | {msg}"
    return base + (f"  {extra_str}" if extra_str else "") + "\n"


def _json_sink(message) -> None:
    """
    Production sink — writes a single JSON line to sys.stdout.
    AWS awslogs driver picks up each line as a separate CloudWatch log event.
    """
    record = message.record
    ts = datetime.fromtimestamp(record["time"].timestamp(), tz=timezone.utc)
    iso_ts = ts.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"

    payload = {
        "timestamp": iso_ts,
        "level": record["level"].name,
        "event": record["extra"].get("event", record["message"]),
        "correlation_id": _correlation_id.get(),
        "logger": record["name"],
        "function": record["function"],
        "line": record["line"],
        "message": record["message"],
    }

    # Merge any extra context fields (user_identifier, provider_response, etc.)
    for k, v in record["extra"].items():
        if k not in payload:
            payload[k] = v

    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def _setup_logger() -> None:
    """Configure Loguru sinks once at import time based on the DEBUG env var."""
    logger.remove()  # Remove Loguru's default stderr sink

    is_debug = os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")

    if is_debug:
        # ── LOCAL: colored stdout ───────────────────────────────────────────
        logger.add(
            sys.stdout,
            format=_local_format,
            level="DEBUG",
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

        # ── LOCAL: rotating file ────────────────────────────────────────────
        os.makedirs("logs", exist_ok=True)
        logger.add(
            "logs/flask_app.log",
            format=_local_format,
            level="DEBUG",
            rotation="10 MB",
            retention="10 days",
            compression="gz",
            backtrace=True,
            diagnose=True,
            encoding="utf-8",
        )
        logger.info(
            "Logger initialised — LOCAL mode (stdout + logs/flask_app.log)",
            event="logger_init",
        )

    else:
        # ── PRODUCTION: JSON stdout only (Docker → CloudWatch) ──────────────
        logger.add(
            _json_sink,
            level="INFO",
            format="{message}",   # raw; _json_sink builds its own JSON
            backtrace=False,
            diagnose=False,
        )
        logger.info(
            "Logger initialised — PRODUCTION mode (JSON stdout only)",
            event="logger_init",
        )


_setup_logger()


# ── Public API ────────────────────────────────────────────────────────────────

def get_logger():
    """
    Return a Loguru logger instance.
    The correlation_id is pulled from the ContextVar automatically on each call.
    """
    return logger
