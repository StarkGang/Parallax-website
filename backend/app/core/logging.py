"""Structured logging and request correlation."""

import logging
import sys
from contextvars import ContextVar
from typing import Any

import structlog

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def _add_request_id(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    req_id = request_id_ctx.get()
    if req_id:
        event_dict["request_id"] = req_id
    return event_dict


def configure_logging(debug: bool = False, json_logs: bool = False) -> None:
    # Windows consoles default to cp1252; structured logs contain Unicode labels.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name or "parallax")


def security_event(event: str, **kwargs: Any) -> None:
    logger = get_logger("security")
    logger.warning(event, **kwargs)

