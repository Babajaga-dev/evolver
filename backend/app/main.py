"""FastAPI application entrypoint.

Avvio: ``uv run uvicorn app.main:app --reload --port 8000``
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.api.v1 import router_v1
from app.core.config import get_settings
from app.core.db import dispose_engine
from app.core.logging import configure_logging, get_logger
from app.core.redis import dispose_redis


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Setup all'avvio, teardown alla chiusura."""
    configure_logging()
    log = get_logger("app.lifespan")
    settings = get_settings()
    log.info(
        "startup",
        env=settings.env,
        version=__version__,
        symbols=settings.symbols,
        timeframes=settings.timeframes,
    )

    yield

    log.info("shutdown")
    await dispose_engine()
    await dispose_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Evolver Backend",
        version=__version__,
        description="Sistema di trading crypto evolutivo — backend API",
        lifespan=lifespan,
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router)
    app.include_router(router_v1)

    return app


app = create_app()
