"""FastAPI application entrypoint.

Avvio: ``uv run uvicorn app.main:app --reload --port 8000``
"""

from __future__ import annotations

import asyncio
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

    # Auto-migrate: alembic upgrade head (idempotente). Sequenziato PRIMA
    # di seed_defaults così la tabella system_settings esiste già.
    # In multi-replica deploy usiamo un Postgres advisory lock per
    # serializzare: una sola replica fa upgrade, le altre attendono e
    # vedono "no-op". Il lock è automaticamente rilasciato quando la
    # connessione si chiude.
    try:
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, text

        def _run_migrations() -> None:
            sync_url = settings.database_url_sync
            engine = create_engine(sync_url, future=True)
            # Connection separata che tiene il lock per tutta la durata di
            # alembic.upgrade. Alembic aprirà internamente le proprie
            # connections, ma il lock advisory è inter-session.
            lock_id = 3842302032
            try:
                lock_conn = engine.connect()
                try:
                    lock_conn.execute(text(f"SELECT pg_advisory_lock({lock_id})"))
                    lock_conn.commit()
                    cfg = Config("alembic.ini")
                    command.upgrade(cfg, "head")
                finally:
                    try:
                        lock_conn.execute(
                            text(f"SELECT pg_advisory_unlock({lock_id})")
                        )
                        lock_conn.commit()
                    finally:
                        lock_conn.close()
            finally:
                engine.dispose()

        await asyncio.to_thread(_run_migrations)
        log.info("alembic.upgrade.done")
    except Exception as exc:  # pragma: no cover
        log.warning("alembic.upgrade.failed", error=str(exc))

    # Seed dei system_settings di default + start dello scheduler
    try:
        from app.system import settings as system_settings
        from app.system.scheduler import start_scheduler

        async with session_scope() as session:
            await system_settings.seed_defaults(session)

        await start_scheduler()
    except Exception as exc:  # pragma: no cover
        log.warning("system.startup.failed", error=str(exc))

    # Resume replay runs interrotti (status='running' o 'pending')
    try:
        import asyncio as _aio
        from app.replay import repo as _replay_repo
        from app.replay.runner import run_replay_task

        async with session_scope() as _s:
            from sqlalchemy import select
            from app.models.replay import ReplayRun
            res = await _s.execute(
                select(ReplayRun).where(ReplayRun.status.in_(("pending", "running")))
            )
            to_resume = list(res.scalars().all())
        for r in to_resume:
            log.info("replay.resume_on_startup", run_id=str(r.id), status=r.status)
            _aio.create_task(run_replay_task(r.id))
    except Exception as exc:
        log.warning("replay.startup_resume.failed", error=str(exc))

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
