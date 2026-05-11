"""Endpoint /api/v1/carry/* — cash-and-carry funding arbitrage."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.carry.engine import CarryConfig, run_cash_and_carry
from app.repositories import ohlcv as ohlcv_repo
from app.repositories import funding as funding_repo
from app.schemas.carry import (
    CarryEquityPoint, CarryResponse, CarryRunRequest, CarryTradeOut,
)

router = APIRouter(prefix="/carry", tags=["carry"])
log = get_logger(__name__)


@router.post("/run", response_model=CarryResponse)
async def run_carry(
    body: CarryRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CarryResponse:
    """Esegue backtest cash-and-carry su (symbol, periodo, params)."""
    # Fetch spot OHLCV
    rows = await ohlcv_repo.fetch_ohlcv(
        session, symbol=body.symbol, timeframe=body.timeframe,
        start=body.start_date, end=body.end_date, limit=50000, order="asc",
    )
    if not rows or len(rows) < 10:
        raise HTTPException(400, f"Dati OHLCV insufficienti per {body.symbol}/{body.timeframe} nel periodo")
    df_spot = pd.DataFrame([{
        "timestamp": r.timestamp, "close": float(r.close),
    } for r in rows]).set_index("timestamp")

    # Fetch funding
    fr_rows = await funding_repo.fetch_funding(
        session, symbol=body.symbol, start=body.start_date, end=body.end_date, limit=50000, order="asc",
    )
    if not fr_rows:
        raise HTTPException(400, f"Funding rates non disponibili per {body.symbol} nel periodo. Triggera /admin/backfill")
    df_funding = pd.DataFrame([{
        "timestamp": r.funding_time, "funding_rate": float(r.funding_rate),
    } for r in fr_rows]).set_index("timestamp")

    log.info("carry.run.start",
             symbol=body.symbol, n_candles=len(df_spot), n_funding=len(df_funding))

    config = CarryConfig(
        symbol=body.symbol,
        initial_cash=body.initial_cash,
        fee_taker=body.fee_taker,
        slippage_bps=body.slippage_bps,
        entry_threshold=body.entry_threshold,
        exit_threshold=body.exit_threshold,
        consecutive_entry=body.consecutive_entry,
        consecutive_exit=body.consecutive_exit,
        position_fraction=body.position_fraction,
        max_drawdown_pct=body.max_drawdown_pct,
    )
    result = run_cash_and_carry(df_spot, df_funding, config)

    log.info("carry.run.done",
             symbol=body.symbol, sharpe=result.sharpe, total_return=result.total_return,
             n_trades=result.n_trades, funding=result.total_funding_collected)

    return CarryResponse(
        symbol=result.symbol,
        start_date=body.start_date,
        end_date=body.end_date,
        n_funding_periods=result.n_funding_periods,
        n_trades=result.n_trades,
        total_funding_collected=result.total_funding_collected,
        total_fees_paid=result.total_fees_paid,
        final_equity=result.final_equity,
        total_return=result.total_return,
        sharpe=result.sharpe,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        apr=result.apr,
        equity_curve=[CarryEquityPoint(**p) for p in result.equity_curve],
        trades=[CarryTradeOut(**t) for t in result.trades],
    )
