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
from app.core.db import dispose_engine, session_scope
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

    # Cleanup GA run orphaned (backend restartato durante run)
    try:
        from app.ga.state import cleanup_stale_running

        n_orphaned = await cleanup_stale_running(max_age_seconds=120)
        if n_orphaned > 0:
            log.warning("ga.cleanup.orphaned_marked_failed", n=n_orphaned)
    except Exception as exc:  # pragma: no cover
        log.warning("ga.cleanup.failed", error=str(exc))

    # Seed dei system_settings di default + start dello scheduler
    try:
        from app.system import settings as system_settings
        from app.system.scheduler import start_scheduler

        async with session_scope() as session:
            await system_settings.seed_defaults(session)

        await start_scheduler()
    except Exception as exc:  # pragma: no cover
        log.warning("system.startup.failed", error=str(exc))

    yield

    log.info("shutdown")
    try:
        from app.system.scheduler import stop_scheduler

        await stop_scheduler()
    except Exception:  # pragma: no cover
        pass
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
