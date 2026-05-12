"""Endpoint /api/v1/statarb/* — pairs trade cointegrazione BTC/ETH market-neutral.

Ref: IJSRA 2026-0283 (BTC-ETH Statistical Arbitrage) Sharpe 1.58-2.45, beta 0.09-0.18.
"""
from __future__ import annotations
from datetime import datetime
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.statarb import (
    StatArbEquityPointOut,
    StatArbMonthlyReturn,
    StatArbResponse,
    StatArbRunRequest,
    StatArbTradeOut,
)
from app.statarb.engine import StatArbConfig, run_statarb_backtest

router = APIRouter(prefix="/statarb", tags=["statarb"])
log = get_logger(__name__)


def _df_from_rows(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"timestamp": r.timestamp, "close": float(r.close)} for r in rows]
    ).set_index("timestamp").sort_index()


@router.post("/run", response_model=StatArbResponse)
async def run_statarb(
    body: StatArbRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StatArbResponse:
    """Backtest pairs trade cointegrazione (symbol_a, symbol_b)."""
    rows_a = await ohlcv_repo.fetch_ohlcv(
        session, symbol=body.symbol_a, timeframe=body.timeframe,
        start=body.start_date, end=body.end_date, limit=200_000, order="asc",
    )
    rows_b = await ohlcv_repo.fetch_ohlcv(
        session, symbol=body.symbol_b, timeframe=body.timeframe,
        start=body.start_date, end=body.end_date, limit=200_000, order="asc",
    )
    if len(rows_a) < body.lookback_bars + 50 or len(rows_b) < body.lookback_bars + 50:
        raise HTTPException(400, f"Dati insufficienti: serve >= {body.lookback_bars+50} bars per simbolo")

    df_a = _df_from_rows(rows_a)
    df_b = _df_from_rows(rows_b)

    config = StatArbConfig(
        symbol_a=body.symbol_a,
        symbol_b=body.symbol_b,
        timeframe=body.timeframe,
        lookback_bars=body.lookback_bars,
        z_entry=body.z_entry,
        z_exit=body.z_exit,
        z_stop=body.z_stop,
        max_half_life_bars=body.max_half_life_bars,
        initial_cash=body.initial_cash,
        capital_per_trade=body.capital_per_trade,
        fee_bps=body.fee_bps,
        slippage_bps=body.slippage_bps,
    )
    log.info("statarb.run.start", a=body.symbol_a, b=body.symbol_b, tf=body.timeframe)
    result = run_statarb_backtest(df_a, df_b, config)
    log.info("statarb.run.done", sharpe=result.sharpe, ret=result.total_return,
             n_trades=result.n_trades, beta_vs_btc=result.beta_vs_btc)

    return StatArbResponse(
        symbol_a=body.symbol_a,
        symbol_b=body.symbol_b,
        timeframe=body.timeframe,
        start_date=result.start_date,
        end_date=result.end_date,
        n_trades=result.n_trades,
        n_winners=result.n_winners,
        initial_cash=result.initial_cash,
        final_equity=result.final_equity,
        total_return=result.total_return,
        sharpe=result.sharpe,
        sortino=result.sortino,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        avg_holding_bars=result.avg_holding_bars,
        beta_vs_btc=result.beta_vs_btc,
        avg_hedge_ratio=result.avg_hedge_ratio,
        cointegration_p_value=result.cointegration_p_value,
        equity_curve=[
            StatArbEquityPointOut(
                t=p.t, equity=p.equity, spread=p.spread, zscore=p.zscore,
                hedge_ratio=p.hedge_ratio, position=p.position,
            ) for p in result.equity_curve
        ],
        trades=[
            StatArbTradeOut(
                entry_time=t.entry_time, exit_time=t.exit_time, side=t.side,
                entry_spread=t.entry_spread, exit_spread=t.exit_spread,
                entry_z=t.entry_z, exit_z=t.exit_z,
                qty_a=t.qty_a, qty_b=t.qty_b,
                pnl=t.pnl, pnl_pct=t.pnl_pct,
                holding_bars=t.holding_bars, reason=t.reason,
            ) for t in result.trades
        ],
        monthly_returns=[StatArbMonthlyReturn(**m) for m in result.monthly_returns],
    )
