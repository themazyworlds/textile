"""
Textile Structured Telemetry & Contextual Logging Subsystem.
Configures structlog for Textile Core & Yarns with contextual variable binding.
"""

import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

lazy import structlog


@dataclass(slots=True)
class _LoggingState:
    initialized: bool = False


_state = _LoggingState()


class LazyLogger:
    """Lazy proxy deferring structlog initialization until the first logging call."""

    __slots__ = ("_name", "_logger")

    def __init__(self, name: str | None = None) -> None:
        self._name = name
        self._logger: Any = None

    def _get_logger(self) -> Any:
        if self._logger is None:
            if not _state.initialized:
                configure_logging()
            self._logger = structlog.get_logger(self._name) if self._name else structlog.get_logger()
        return self._logger

    def debug(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().debug(event, **kw)

    def info(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().info(event, **kw)

    def warning(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().warning(event, **kw)

    def error(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().error(event, **kw)

    def critical(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().critical(event, **kw)

    def exception(self, event: str | None = None, **kw: Any) -> Any:
        return self._get_logger().exception(event, **kw)

    def bind(self, **kw: Any) -> Any:
        return self._get_logger().bind(**kw)

    def unbind(self, *keys: str) -> Any:
        return self._get_logger().unbind(*keys)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._get_logger(), item)


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


def get_logger(name: str | None = None) -> Any:
    """Get a structured logger instance, optionally named."""
    return LazyLogger(name)
