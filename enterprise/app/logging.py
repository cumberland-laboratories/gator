"""Structured logging configuration for Enterprise API and worker."""

import logging
import sys

import structlog

_configured = False


def configure_logging(app_env: str = "dev") -> None:
    """Configure structlog. JSON in prod, console in dev."""
    global _configured
    if _configured:
        return
    _configured = True

    # Shared processors
    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if app_env == "dev":
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "gator.enterprise") -> structlog.BoundLogger:
    """Get a bound structlog logger."""
    return structlog.get_logger(name)
