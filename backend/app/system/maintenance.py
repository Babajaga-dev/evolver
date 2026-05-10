"""Maintenance helpers — stats DB e cleanup operazionali.

Tutte le delete pericolose accettano un ``confirm`` flag per evitare wipe
accidentali via API. Le operazioni di cleanup sono pensate per uso admin
manuale dal pannello /control.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.ga import state as ga_state
from app.models.market import OHLCV
from app.models.strategy import (
    FitnessEvaluation,
    Generation,
    Population,
    Strategy,
)

log = get_logger(__name__)


CleanupTarget = Literal[
    "ohlcv_old",
    "ga_runs_failed",
    "ga_runs_completed",
    "ga_runs_all",
]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def collect_stats(session: AsyncSession) -> dict[str, Any]:
    """Snapshot dei counts per tabella + Redis GA runs.

    Pensato per il pannello /control: vista d'insieme dello stato del sistema.
    """

    async def _count(model: Any) -> int:
        q = await session.execute(select(func.count()).select_from(model))
        return int(q.scalar_one())

    ohlcv_count = await _count(OHLCV)
    populations_count = await _count(Population)
    generations_count = await _count(Generation)
    strategies_count = await _count(Strategy)
    fitness_count = await _count(FitnessEvaluation)

    # OHLCV: oldest / newest per dare un'idea dell'estensione storica
    oldest_q = await session.execute(select(func.min(OHLCV.timestamp)))
    newest_q = await session.execute(select(func.max(OHLCV.timestamp)))
    ohlcv_oldest = oldest_q.scalar()
    ohlcv_newest = newest_q.scalar()

    # GA runs Redis
    ga_states = await ga_state.list_states(limit=500)
    ga_by_status: dict[str, int] = {}
    for s in ga_states:
        ga_by_status[s.status] = ga_by_status.get(s.status, 0) + 1

    return {
        "ohlcv": {
            "count": ohlcv_count,
            "oldest": ohlcv_oldest.isoformat() if ohlcv_oldest else None,
            "newest": ohlcv_newest.isoformat() if ohlcv_newest else None,
        },
        "news": {"raw": 0, "scored": 0, "pending": 0},
        "ga_postgres": {
            "populations": populations_count,
            "generations": generations_count,
            "strategies": strategies_count,
            "fitness_evaluations": fitness_count,
        },
        "ga_redis": {
            "total": len(ga_states),
            "by_status": ga_by_status,
        },
    }


# ---------------------------------------------------------------------------
# Cleanup operations
# ---------------------------------------------------------------------------


async def cleanup(
    session: AsyncSession,
    *,
    target: CleanupTarget,
    older_than_days: int | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Esegue una cleanup operation con safety check.

    Args:
        session: AsyncSession (caller gestisce commit).
        target: cosa pulire (vedi ``CleanupTarget``).
        older_than_days: soglia per cleanup time-based (ohlcv_old).
                         Se None, default sicuri (365d ohlcv, 30d news).
        confirm: deve essere ``True`` per eseguire la delete. Senza, dry-run
                 che ritorna solo la count di righe candidate.

    Returns:
        {"target": str, "deleted": int, "dry_run": bool, "details": dict}
    """
    if target == "ohlcv_old":
        return await _cleanup_ohlcv_old(
            session, older_than_days or 365, confirm=confirm
        )
    if target == "ga_runs_failed":
        return await _cleanup_ga_runs(session, status_filter="failed", confirm=confirm)
    if target == "ga_runs_completed":
        return await _cleanup_ga_runs(
            session, status_filter="completed", confirm=confirm
        )
    if target == "ga_runs_all":
        return await _cleanup_ga_runs(session, status_filter=None, confirm=confirm)

    raise ValueError(f"Cleanup target sconosciuto: {target}")


# ---------------------------------------------------------------------------
# Internal cleanup implementations
# ---------------------------------------------------------------------------


async def _cleanup_ohlcv_old(
    session: AsyncSession,
    older_than_days: int,
    *,
    confirm: bool,
) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    count_q = await session.execute(
        select(func.count()).select_from(OHLCV).where(OHLCV.timestamp < cutoff)
    )
    n_candidates = int(count_q.scalar_one())

    if not confirm:
        return {
            "target": "ohlcv_old",
            "deleted": 0,
            "dry_run": True,
            "details": {"candidates": n_candidates, "cutoff": cutoff.isoformat()},
        }

    result = await session.execute(delete(OHLCV).where(OHLCV.timestamp < cutoff))
    deleted = result.rowcount or 0
    log.warning("system.cleanup.ohlcv_old", deleted=deleted, cutoff=cutoff.isoformat())
    return {
        "target": "ohlcv_old",
        "deleted": deleted,
        "dry_run": False,
        "details": {"cutoff": cutoff.isoformat()},
    }




async def _cleanup_ga_runs(
    session: AsyncSession,
    *,
    status_filter: str | None,
    confirm: bool,
) -> dict[str, Any]:
    """Cleanup dei GA run salvati su Redis (state pickle).

    Non tocca i run in pending/running per evitare disallineamento.
    """
    states = await ga_state.list_states(limit=500)
    candidates = [
        s
        for s in states
        if (status_filter is None or s.status == status_filter)
        and s.status not in {"pending", "running"}
    ]
    target_label = (
        f"ga_runs_{status_filter}" if status_filter else "ga_runs_all"
    )

    if not confirm:
        return {
            "target": target_label,
            "deleted": 0,
            "dry_run": True,
            "details": {
                "candidates": len(candidates),
                "ids": [s.population_id for s in candidates[:20]],
            },
        }

    deleted_ids: list[str] = []
    for s in candidates:
        ok = await ga_state.delete_state(s.population_id)
        if ok:
            deleted_ids.append(s.population_id)

    log.warning("system.cleanup.ga_runs", deleted=len(deleted_ids), filter=status_filter)
    return {
        "target": target_label,
        "deleted": len(deleted_ids),
        "dry_run": False,
        "details": {"ids": deleted_ids},
    }
