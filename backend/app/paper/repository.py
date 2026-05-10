"""Repository helpers per paper trading: trades + equity snapshots."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.paper import EquitySnapshot, PaperTrade

log = get_logger(__name__)


async def list_paper_trades(
    session: AsyncSession,
    *,
    limit: int = 100,
    status: str | None = None,
) -> list[PaperTrade]:
    """Lista trade paper ordered by entry_time DESC."""
    stmt = select(PaperTrade).order_by(desc(PaperTrade.entry_time)).limit(limit)
    if status:
        stmt = stmt.where(PaperTrade.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_equity_curve(
    session: AsyncSession,
    *,
    portfolio_id: str = "paper-v1",
    hours: int = 168,
    max_points: int = 500,
) -> list[EquitySnapshot]:
    """Equity curve per il chart frontend."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    stmt = (
        select(EquitySnapshot)
        .where(
            EquitySnapshot.portfolio_id == portfolio_id,
            EquitySnapshot.timestamp >= cutoff,
        )
        .order_by(EquitySnapshot.timestamp.asc())
        .limit(max_points)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_paper_state(
    session: AsyncSession,
    *,
    portfolio_id: str = "paper-v1",
) -> dict[str, Any]:
    """Snapshot corrente del portfolio per il pannello /paper."""
    settings = get_settings()
    initial = float(settings.paper_initial_balance_usdt)

    last_q = await session.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.portfolio_id == portfolio_id)
        .order_by(desc(EquitySnapshot.timestamp))
        .limit(1)
    )
    last = last_q.scalar_one_or_none()

    open_count_q = await session.execute(
        select(func.count())
        .select_from(PaperTrade)
        .where(PaperTrade.status == "open")
    )
    open_count = int(open_count_q.scalar_one())

    closed_count_q = await session.execute(
        select(func.count())
        .select_from(PaperTrade)
        .where(PaperTrade.status != "open")
    )
    closed_count = int(closed_count_q.scalar_one())

    winning_q = await session.execute(
        select(func.count())
        .select_from(PaperTrade)
        .where(PaperTrade.status != "open", PaperTrade.pnl > 0)
    )
    winning = int(winning_q.scalar_one())

    total_pnl_q = await session.execute(
        select(func.coalesce(func.sum(PaperTrade.pnl), 0))
        .select_from(PaperTrade)
        .where(PaperTrade.pnl.is_not(None))
    )
    total_pnl = float(total_pnl_q.scalar_one() or 0.0)

    if last is None:
        return {
            "portfolio_id": portfolio_id,
            "initial_balance": initial,
            "balance_quote": initial,
            "holdings": {},
            "equity": initial,
            "drawdown_from_peak": 0.0,
            "open_positions_count": 0,
            "last_snapshot_at": None,
            "total_return_pct": 0.0,
            "trades_total": closed_count + open_count,
            "trades_open": open_count,
            "trades_closed": closed_count,
            "trades_winning": winning,
            "win_rate": (winning / closed_count) if closed_count > 0 else 0.0,
            "total_pnl": total_pnl,
            "status": "uninitialized",
        }

    equity = float(last.equity)
    return {
        "portfolio_id": last.portfolio_id,
        "initial_balance": initial,
        "balance_quote": float(last.balance_quote),
        "holdings": dict(last.holdings or {}),
        "equity": equity,
        "drawdown_from_peak": float(last.drawdown_from_peak),
        "open_positions_count": int(last.open_positions_count),
        "last_snapshot_at": last.timestamp.isoformat(),
        "total_return_pct": ((equity - initial) / initial * 100) if initial > 0 else 0.0,
        "trades_total": closed_count + open_count,
        "trades_open": open_count,
        "trades_closed": closed_count,
        "trades_winning": winning,
        "win_rate": (winning / closed_count) if closed_count > 0 else 0.0,
        "total_pnl": total_pnl,
        "status": "active",
    }


async def create_initial_snapshot(
    session: AsyncSession,
    *,
    portfolio_id: str = "paper-v1",
) -> EquitySnapshot:
    """Crea snapshot di partenza con il balance iniziale config."""
    settings = get_settings()
    initial = Decimal(str(settings.paper_initial_balance_usdt))

    snap = EquitySnapshot(
        timestamp=datetime.now(timezone.utc),
        portfolio_id=portfolio_id,
        balance_quote=initial,
        holdings={},
        equity=initial,
        drawdown_from_peak=0.0,
        open_positions_count=0,
    )
    session.add(snap)
    await session.flush()
    log.info("paper.snapshot.initial", portfolio_id=portfolio_id, equity=str(initial))
    return snap
