"""
Textile Structured Telemetry & Contextual Logging Subsystem.
Configures structlog for Textile Core & Yarns with contextual variable binding.
"""

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

import structlog


@dataclass(slots=True)
class _LoggingState:
    initialized: bool = False


_state = _LoggingState()


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog processors and standard library logging integration."""
    if _state.initialized:
        return

    log_format = os.environ.get("TEXTILE_LOG_FORMAT", "console").lower()
    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _state.initialized = True


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structured logger instance, optionally named."""
    if not _state.initialized:
        configure_logging()
    return structlog.get_logger(name) if name else structlog.get_logger()
