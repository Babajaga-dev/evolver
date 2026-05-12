"""Endpoint /api/v1/trend/* — Donchian ensemble multi-asset backtest.

Ref: AdaptiveTrend arXiv 2602.11708 (Feb 2026) — Sharpe 2.41 OOS 2022-2024.
"""
from __future__ import annotations
from datetime import datetime
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.trend import (
    TrendAssetStat,
    TrendEquityPoint,
    TrendMonthlyReturn,
    TrendResponse,
    TrendRunRequest,
    TrendTradeOut,
)
from app.trend.engine import TrendConfig, run_trend_backtest

router = APIRouter(prefix="/trend", tags=["trend"])
log = get_logger(__name__)


def _bppy(tf: str) -> int:
    return {"1h": 24 * 365, "4h": 6 * 365, "1d": 365}.get(tf, 365)


def _buy_hold_baseline(df: pd.DataFrame, initial_cash: float, bppy: int) -> dict:
    if df.empty or len(df) < 5:
        return {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "final_equity": initial_cash}
    px = df["close"]
    eq = px / px.iloc[0] * initial_cash
    rets = eq.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(bppy)) if rets.std() > 0 else 0.0
    peak = eq.cummax()
    dd = float(((eq - peak) / peak).min())
    return {
        "sharpe": sharpe,
        "total_return": float((eq.iloc[-1] / initial_cash) - 1),
        "max_drawdown": dd,
        "final_equity": float(eq.iloc[-1]),
    }


@router.post("/run", response_model=TrendResponse)
async def run_trend(
    body: TrendRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TrendResponse:
    """Esegue backtest TREND multi-asset Donchian ensemble."""
    # Fetch OHLCV per simbolo
    ohlcv_by_sym: dict[str, pd.DataFrame] = {}
    for sym in body.symbols:
        rows = await ohlcv_repo.fetch_ohlcv(
            session, symbol=sym, timeframe=body.timeframe,
            start=body.start_date, end=body.end_date, limit=200_000, order="asc",
        )
        if len(rows) < max(body.lookbacks) + 5:
            log.warning("trend.run.skip_symbol", symbol=sym, n_rows=len(rows))
            continue
        df = pd.DataFrame(
            [{"timestamp": r.timestamp, "open": float(r.open), "high": float(r.high),
              "low": float(r.low), "close": float(r.close), "volume": float(r.volume)} for r in rows]
        ).set_index("timestamp").sort_index()
        ohlcv_by_sym[sym] = df

    if not ohlcv_by_sym:
        raise HTTPException(400, "Nessun simbolo con dati sufficienti nel range")

    config = TrendConfig(
        symbols=list(ohlcv_by_sym.keys()),
        timeframe=body.timeframe,
        lookbacks=tuple(body.lookbacks),
        target_vol_annual=body.target_vol_annual,
        trailing_stop_atr_mult=body.trailing_stop_atr_mult,
        rebalance_days=body.rebalance_days,
        top_n_assets=body.top_n_assets,
        long_weight=body.long_weight,
        short_weight=body.short_weight,
        fee_bps=body.fee_bps,
        slippage_bps=body.slippage_bps,
        initial_cash=body.initial_cash,
    )
    log.info("trend.run.start", symbols=list(ohlcv_by_sym.keys()),
             tf=body.timeframe, start=body.start_date.isoformat(),
             end=body.end_date.isoformat())
    result = run_trend_backtest(ohlcv_by_sym, config)
    log.info("trend.run.done", sharpe=result.sharpe, ret=result.total_return,
             n_trades=result.n_trades, max_dd=result.max_drawdown)

    # Baselines: B&H equal-weighted basket
    bppy = _bppy(body.timeframe)
    bh_per_asset = []
    for sym, df in ohlcv_by_sym.items():
        bh_per_asset.append(_buy_hold_baseline(df, body.initial_cash, bppy))
    bh_combined = {
        "sharpe": float(np.mean([b["sharpe"] for b in bh_per_asset])),
        "total_return": float(np.mean([b["total_return"] for b in bh_per_asset])),
        "max_drawdown": float(np.min([b["max_drawdown"] for b in bh_per_asset])),
        "final_equity": float(np.mean([b["final_equity"] for b in bh_per_asset])),
    }

    return TrendResponse(
        symbols=list(ohlcv_by_sym.keys()),
        timeframe=body.timeframe,
        start_date=result.start_date,
        end_date=result.end_date,
        n_trades=result.n_trades,
        n_long_trades=result.n_long_trades,
        n_short_trades=result.n_short_trades,
        initial_cash=result.initial_cash,
        final_equity=result.final_equity,
        total_return=result.total_return,
        sharpe=result.sharpe,
        sortino=result.sortino,
        max_drawdown=result.max_drawdown,
        win_rate=result.win_rate,
        avg_pnl_pct=result.avg_pnl_pct,
        monthly_returns=[TrendMonthlyReturn(**m) for m in result.monthly_returns],
        equity_curve=[TrendEquityPoint(**p) for p in result.equity_curve],
        trades=[
            TrendTradeOut(
                symbol=t.symbol, side=t.side,
                entry_time=t.entry_time, entry_price=t.entry_price,
                exit_time=t.exit_time, exit_price=t.exit_price,
                pnl=t.pnl, pnl_pct=t.pnl_pct,
                holding_days=t.holding_days, reason=t.reason,
            ) for t in result.trades
        ],
        per_asset_stats=[TrendAssetStat(**a) for a in result.per_asset_stats],
        baselines={
            "buy_hold_equal_weight": bh_combined,
            "per_asset_buy_hold": [
                {"symbol": sym, **bh_per_asset[i]}
                for i, sym in enumerate(ohlcv_by_sym.keys())
            ],
        },
    )
