"""Endpoint /api/v1/paper/* — paper trading dashboard read-only.

Slice 4.0a: scaffold. Il paper engine che genera trade/snapshots
arriva in slice successiva. Per ora qui esponiamo solo lo stato del DB.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.paper import (
    create_initial_snapshot,
    get_paper_state,
    list_equity_curve,
    list_paper_trades,
)
from app.schemas.paper import (
    EquityCurveResponse,
    EquityPoint,
    PaperSnapshotResponse,
    PaperStateResponse,
    PaperTradeOut,
    PaperTradesResponse,
)

router = APIRouter(tags=["paper"], prefix="/paper")
log = get_logger(__name__)


@router.get("/state", response_model=PaperStateResponse)
async def paper_state(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    portfolio_id: str = Query(default="paper-v1"),
) -> PaperStateResponse:
    """Snapshot dello stato corrente del portfolio paper."""
    state = await get_paper_state(session, portfolio_id=portfolio_id)
    return PaperStateResponse(**state)


@router.get("/trades", response_model=PaperTradesResponse)
async def paper_trades(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=100, ge=1, le=1000),
    status: str | None = Query(default=None),
) -> PaperTradesResponse:
    """Lista paper trades ordinati per entry_time DESC."""
    rows = await list_paper_trades(session, limit=limit, status=status)
    items = [
        PaperTradeOut(
            id=t.id,
            strategy_id=t.strategy_id,
            symbol=t.symbol,
            timeframe=t.timeframe,
            side=t.side,
            status=t.status,
            quantity=float(t.quantity),
            entry_price=float(t.entry_price),
            exit_price=float(t.exit_price) if t.exit_price is not None else None,
            entry_time=t.entry_time,
            exit_time=t.exit_time,
            fees=float(t.fees),
            pnl=float(t.pnl) if t.pnl is not None else None,
            pnl_pct=t.pnl_pct,
        )
        for t in rows
    ]
    return PaperTradesResponse(trades=items, count=len(items))


@router.get("/equity", response_model=EquityCurveResponse)
async def paper_equity(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    portfolio_id: str = Query(default="paper-v1"),
    hours: int = Query(default=168, ge=1, le=8760),
    max_points: int = Query(default=500, ge=10, le=2000),
) -> EquityCurveResponse:
    """Equity curve con snapshot timeseries."""
    rows = await list_equity_curve(
        session,
        portfolio_id=portfolio_id,
        hours=hours,
        max_points=max_points,
    )
    points = [
        EquityPoint(
            timestamp=r.timestamp,
            equity=float(r.equity),
            balance_quote=float(r.balance_quote),
            drawdown_from_peak=float(r.drawdown_from_peak),
            open_positions_count=int(r.open_positions_count),
        )
        for r in rows
    ]
    return EquityCurveResponse(
        portfolio_id=portfolio_id, points=points, count=len(points)
    )


@router.post("/snapshot", response_model=PaperSnapshotResponse)
async def paper_create_initial_snapshot(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    portfolio_id: str = Query(default="paper-v1"),
) -> PaperSnapshotResponse:
    """Crea uno snapshot di equity con il balance iniziale config."""
    snap = await create_initial_snapshot(session, portfolio_id=portfolio_id)
    await session.commit()
    return PaperSnapshotResponse(
        portfolio_id=snap.portfolio_id,
        snapshot_at=snap.timestamp,
        equity=float(snap.equity),
        message=f"Initial snapshot created with equity {float(snap.equity)} USDT",
    )
