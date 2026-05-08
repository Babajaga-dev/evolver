"""Query repository per OHLCV — un layer sopra SQLAlchemy.

Gli endpoint API NON parlano direttamente con SQLAlchemy: passano sempre
da qui. Vantaggi:
    - test/mock più semplici
    - cambi schema isolati
    - log/metriche centralizzate
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market import OHLCV


async def fetch_ohlcv(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 500,
    order: str = "asc",
) -> list[OHLCV]:
    """Lista candele per (symbol, timeframe) nell'intervallo richiesto.

    Args:
        symbol: es. "BTC/USDT".
        timeframe: es. "4h".
        start: lower bound timestamp (incluso). Default ``end - 30 days``.
        end: upper bound timestamp (incluso). Default ``now``.
        limit: max righe (cap a 5000 a livello API).
        order: ``asc`` o ``desc``.

    Returns:
        Lista di OHLCV — già fully-loaded (no lazy).
    """
    if end is None:
        end = datetime.now(timezone.utc)
    if start is None:
        start = end - timedelta(days=30)

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    order_col = OHLCV.timestamp.asc() if order == "asc" else OHLCV.timestamp.desc()

    stmt = (
        select(OHLCV)
        .where(
            OHLCV.symbol == symbol,
            OHLCV.timeframe == timeframe,
            OHLCV.timestamp >= start,
            OHLCV.timestamp <= end,
        )
        .order_by(order_col)
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_candles(
    session: AsyncSession,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> int:
    """Conteggio candele in DB (usato per status/healthcheck dati)."""
    stmt = select(func.count()).select_from(OHLCV)
    if symbol is not None:
        stmt = stmt.where(OHLCV.symbol == symbol)
    if timeframe is not None:
        stmt = stmt.where(OHLCV.timeframe == timeframe)
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def latest_timestamp(
    session: AsyncSession,
    symbol: str,
    timeframe: str,
) -> datetime | None:
    """Timestamp dell'ultima candela disponibile per (symbol, timeframe)."""
    stmt = (
        select(OHLCV.timestamp)
        .where(OHLCV.symbol == symbol, OHLCV.timeframe == timeframe)
        .order_by(OHLCV.timestamp.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def coverage_summary(
    session: AsyncSession,
) -> list[dict]:
    """Riassunto per (symbol, timeframe): count, first ts, last ts.

    Usato dalla pagina /data per mostrare quanto storico è disponibile.
    """
    stmt = (
        select(
            OHLCV.symbol,
            OHLCV.timeframe,
            func.count().label("count"),
            func.min(OHLCV.timestamp).label("first"),
            func.max(OHLCV.timestamp).label("last"),
        )
        .group_by(OHLCV.symbol, OHLCV.timeframe)
        .order_by(OHLCV.symbol, OHLCV.timeframe)
    )
    result = await session.execute(stmt)
    return [
        {
            "symbol": row.symbol,
            "timeframe": row.timeframe,
            "count": row.count,
            "first": row.first,
            "last": row.last,
        }
        for row in result.all()
    ]
