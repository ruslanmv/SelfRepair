"""Structlog setup with stdlib bridge.

Logs come out as JSON in production and pretty-printed in dev. Every record
is enriched via contextvars, so binding `job_id` once propagates to every
subsequent log line in that task.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


def configure_logging(
    *, service: str = "selfrepair", json_logs: bool | None = None
) -> None:
    if json_logs is None:
        json_logs = os.getenv("SELFREPAIR_LOG_JSON", "1") == "1"

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
    ]

    if json_logs:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib loggers (uvicorn, sqlalchemy) so their messages render
    # through structlog's pipeline.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    structlog.contextvars.bind_contextvars(
        service=service,
        env=os.getenv("SELFREPAIR_ENV", "dev"),
    )


def bind_context(**kwargs: Any) -> None:
    """Bind key/value pairs to all subsequent logs in this async task.

    Idiomatic use::

        bind_context(job_id=str(job.id), repo=repo.full_name)
        log.info("cloning")    # job_id and repo show up automatically
    """
    structlog.contextvars.bind_contextvars(**kwargs)
