"""Repository per FundingRate."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.funding import FundingRate


async def fetch_funding(
    session: AsyncSession, symbol: str, *,
    start: datetime | None = None, end: datetime | None = None,
    limit: int = 50000, order: str = "asc",
) -> list[FundingRate]:
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=30)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    order_col = FundingRate.funding_time.asc() if order == "asc" else FundingRate.funding_time.desc()
    stmt = (
        select(FundingRate)
        .where(FundingRate.symbol == symbol, FundingRate.funding_time >= start, FundingRate.funding_time <= end)
        .order_by(order_col).limit(limit)
    )
    res = await session.execute(stmt)
    return list(res.scalars().all())


async def count_funding(session: AsyncSession, symbol: str | None = None) -> int:
    stmt = select(func.count()).select_from(FundingRate)
    if symbol:
        stmt = stmt.where(FundingRate.symbol == symbol)
    res = await session.execute(stmt)
    return int(res.scalar_one() or 0)


async def upsert_funding(
    session: AsyncSession, *, rows: list[dict],
) -> int:
    """Upsert idempotente. Rows: {symbol, funding_time, funding_rate, mark_price}."""
    if not rows:
        return 0
    stmt = pg_insert(FundingRate).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "funding_time"])
    res = await session.execute(stmt)
    await session.commit()
    return res.rowcount or 0


async def latest_funding_time(session: AsyncSession, symbol: str) -> datetime | None:
    stmt = select(func.max(FundingRate.funding_time)).where(FundingRate.symbol == symbol)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()
