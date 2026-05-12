"""Repository per fng_index (Fear & Greed Index)."""
from __future__ import annotations
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sentiment import FngIndex


async def upsert_fng(session: AsyncSession, *, rows: list[dict]) -> int:
    """Insert idempotente (ON CONFLICT DO NOTHING)."""
    if not rows:
        return 0
    stmt = pg_insert(FngIndex).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["fng_date"])
    result = await session.execute(stmt)
    return result.rowcount or 0


async def fetch_fng(
    session: AsyncSession,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 50_000,
    order: str = "asc",
) -> Sequence[FngIndex]:
    """Fetch FNG entries nel range, ordinati per data."""
    q = select(FngIndex)
    if start is not None:
        q = q.where(FngIndex.fng_date >= start)
    if end is not None:
        q = q.where(FngIndex.fng_date <= end)
    if order == "asc":
        q = q.order_by(FngIndex.fng_date.asc())
    else:
        q = q.order_by(FngIndex.fng_date.desc())
    q = q.limit(limit)
    result = await session.execute(q)
    return result.scalars().all()


async def count_fng(session: AsyncSession) -> int:
    from sqlalchemy import func
    q = select(func.count(FngIndex.fng_date))
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def latest_fng(session: AsyncSession) -> FngIndex | None:
    q = select(FngIndex).order_by(FngIndex.fng_date.desc()).limit(1)
    r = await session.execute(q)
    return r.scalar_one_or_none()
