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
from app.models.market import OHLCV
log = get_logger(__name__)


CleanupTarget = Literal["ohlcv_old"]


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

    # OHLCV: oldest / newest per dare un'idea dell'estensione storica
    oldest_q = await session.execute(select(func.min(OHLCV.timestamp)))
    newest_q = await session.execute(select(func.max(OHLCV.timestamp)))
    ohlcv_oldest = oldest_q.scalar()
    ohlcv_newest = newest_q.scalar()

    return {
        "ohlcv": {
            "count": ohlcv_count,
            "oldest": ohlcv_oldest.isoformat() if ohlcv_oldest else None,
            "newest": ohlcv_newest.isoformat() if ohlcv_newest else None,
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
                         Se None, default sicuro (365d ohlcv).
        confirm: deve essere ``True`` per eseguire la delete. Senza, dry-run
                 che ritorna solo la count di righe candidate.

    Returns:
        {"target": str, "deleted": int, "dry_run": bool, "details": dict}
    """
    if target == "ohlcv_old":
        return await _cleanup_ohlcv_old(
            session, older_than_days or 365, confirm=confirm
        )

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




