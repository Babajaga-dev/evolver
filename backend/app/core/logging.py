"""Structured logging setup via structlog.

Output JSON in prod (parsing automatico da Dokploy/Loki), pretty colorato in dev.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Configura structlog + standard logging.

    Idempotente: chiamare a ogni boot worker / process.
    """
    settings = get_settings()
    level = getattr(logging, settings.log_level)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.is_prod or not settings.debug:
        # Prod: JSON line-delimited, parsabile da Loki/Datadog/Dokploy logs
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        # Dev: pretty, con colori
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Allinea il logging stdlib (uvicorn, sqlalchemy, ecc.) al renderer scelto
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Silenzia rumorose librerie a meno di debug esplicito
    for noisy in ("uvicorn.access", "asyncio", "ccxt"):
        logging.getLogger(noisy).setLevel(
            logging.DEBUG if settings.debug else logging.WARNING
        )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Helper per ottenere un logger structlog tipato."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
