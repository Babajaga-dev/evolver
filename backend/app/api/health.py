"""Healthcheck endpoint.

Verifica che backend, DB e Redis siano raggiungibili. Usato da Docker
healthcheck e da Dokploy per il routing Traefik.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status
from sqlalchemy import text

from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.redis import get_redis

router = APIRouter(tags=["health"])
log = get_logger(__name__)


@router.get("/health", status_code=status.HTTP_200_OK)
async def health() -> dict[str, Any]:
    """Liveness + readiness combined.

    Returns 200 con flag dei dipendenti. Non solleva: anche se Postgres è
    down, il container risponde 200 con ``database: false`` — Dokploy gestisce
    il routing in base al flag.
    """
    db_ok = False
    timescale_ok = False
    redis_ok = False

    # --- Database ---
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
            db_ok = True
            # Verifica anche estensione TimescaleDB
            res = await session.execute(
                text(
                    "SELECT extname FROM pg_extension WHERE extname = 'timescaledb'"
                )
            )
            timescale_ok = res.scalar_one_or_none() is not None
    except Exception as exc:  # noqa: BLE001
        log.warning("health.db_failed", error=str(exc))

    # --- Redis ---
    try:
        redis = get_redis()
        pong = await redis.ping()
        redis_ok = bool(pong)
    except Exception as exc:  # noqa: BLE001
        log.warning("health.redis_failed", error=str(exc))

    overall = "ok" if (db_ok and redis_ok) else "degraded"

    return {
        "status": overall,
        "database": db_ok,
        "timescale": timescale_ok,
        "redis": redis_ok,
    }


@router.get("/version")
async def version() -> dict[str, str]:
    from app import __version__

    return {"version": __version__, "service": "evolver-backend"}
