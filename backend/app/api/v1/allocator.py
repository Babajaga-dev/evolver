"""Endpoint /api/v1/allocator/* — combine Trend + StatArb + Carry con risk parity + overlays."""
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
from app.repositories import funding as funding_repo
from app.repositories import sentiment as sentiment_repo
from app.allocator.engine import AllocatorConfig, AllocatorPointOut, run_allocator
from app.schemas.allocator import (
    AllocatorPointOut as APO,
    AllocatorResponse,
    AllocatorRunRequest,
)
from app.trend.engine import TrendConfig, run_trend_backtest
from app.statarb.engine import StatArbConfig, run_statarb_backtest
from app.carry.engine import CarryConfig, run_cash_and_carry

router = APIRouter(prefix="/allocator", tags=["allocator"])
log = get_logger(__name__)


def _ohlcv_to_df(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"timestamp": r.timestamp, "open": float(r.open), "high": float(r.high),
          "low": float(r.low), "close": float(r.close), "volume": float(r.volume)} for r in rows]
    ).set_index("timestamp").sort_index()


@router.post("/run", response_model=AllocatorResponse)
async def run_allocator_backtest(
    body: AllocatorRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AllocatorResponse:
    """Esegue backtest combinato Trend + StatArb + Carry con risk parity + overlays."""
    engines_equity: dict[str, pd.DataFrame] = {}
    per_engine_metrics: dict[str, dict] = {}

    # 1. TREND
    if body.run_trend:
        ohlcv_by_sym: dict[str, pd.DataFrame] = {}
        for sym in body.symbols:
            rows = await ohlcv_repo.fetch_ohlcv(
                session, symbol=sym, timeframe=body.timeframe,
                start=body.start_date, end=body.end_date, limit=200_000, order="asc",
            )
            if len(rows) > 250:
                ohlcv_by_sym[sym] = _ohlcv_to_df(rows)
        if ohlcv_by_sym:
            try:
                config_t = TrendConfig(
                    symbols=list(ohlcv_by_sym.keys()),
                    timeframe=body.timeframe,
                    top_n_assets=min(10, len(ohlcv_by_sym)),
                    initial_cash=10_000.0,
                )
                res_t = run_trend_backtest(ohlcv_by_sym, config_t)
                engines_equity["trend"] = pd.DataFrame(
                    [{"t": p["t"], "equity": p["equity"]} for p in res_t.equity_curve]
                ).set_index("t")
                per_engine_metrics["trend"] = {
                    "sharpe": res_t.sharpe, "return": res_t.total_return,
                    "max_drawdown": res_t.max_drawdown, "n_trades": res_t.n_trades,
                }
                log.info("allocator.trend.done", sharpe=res_t.sharpe, ret=res_t.total_return)
            except Exception as ex:
                log.exception("allocator.trend.failed", error=str(ex))

    # 2. STAT-ARB BTC/ETH
    if body.run_statarb:
        rows_a = await ohlcv_repo.fetch_ohlcv(
            session, symbol=body.statarb_symbol_a, timeframe=body.timeframe,
            start=body.start_date, end=body.end_date, limit=200_000, order="asc",
        )
        rows_b = await ohlcv_repo.fetch_ohlcv(
            session, symbol=body.statarb_symbol_b, timeframe=body.timeframe,
            start=body.start_date, end=body.end_date, limit=200_000, order="asc",
        )
        if len(rows_a) > 200 and len(rows_b) > 200:
            df_a = pd.DataFrame([{"timestamp": r.timestamp, "close": float(r.close)} for r in rows_a]).set_index("timestamp")
            df_b = pd.DataFrame([{"timestamp": r.timestamp, "close": float(r.close)} for r in rows_b]).set_index("timestamp")
            try:
                config_s = StatArbConfig(
                    symbol_a=body.statarb_symbol_a, symbol_b=body.statarb_symbol_b,
                    timeframe=body.timeframe, initial_cash=10_000.0,
                )
                res_s = run_statarb_backtest(df_a, df_b, config_s)
                engines_equity["statarb"] = pd.DataFrame(
                    [{"t": p.t, "equity": p.equity} for p in res_s.equity_curve]
                ).set_index("t")
                per_engine_metrics["statarb"] = {
                    "sharpe": res_s.sharpe, "return": res_s.total_return,
                    "max_drawdown": res_s.max_drawdown, "n_trades": res_s.n_trades,
                    "beta_vs_btc": res_s.beta_vs_btc,
                }
                log.info("allocator.statarb.done", sharpe=res_s.sharpe)
            except Exception as ex:
                log.exception("allocator.statarb.failed", error=str(ex))

    # 3. CARRY (BTC funding)
    if body.run_carry:
        rows_btc = await ohlcv_repo.fetch_ohlcv(
            session, symbol="BTC/USDT", timeframe=body.timeframe,
            start=body.start_date, end=body.end_date, limit=200_000, order="asc",
        )
        fr_rows = await funding_repo.fetch_funding(
            session, symbol="BTC/USDT", start=body.start_date, end=body.end_date,
            limit=50_000, order="asc",
        )
        if rows_btc and fr_rows:
            df_btc = pd.DataFrame([{"timestamp": r.timestamp, "close": float(r.close)} for r in rows_btc]).set_index("timestamp")
            df_fund = pd.DataFrame([{"timestamp": r.funding_time, "funding_rate": float(r.funding_rate)} for r in fr_rows]).set_index("timestamp")
            try:
                config_c = CarryConfig(symbol="BTC/USDT", initial_cash=10_000.0)
                res_c = run_cash_and_carry(df_btc, df_fund, config_c)
                engines_equity["carry"] = pd.DataFrame(
                    [{"t": p["t"], "equity": p["equity"]} for p in res_c.equity_curve]
                ).set_index("t")
                per_engine_metrics["carry"] = {
                    "sharpe": res_c.sharpe, "return": res_c.total_return,
                    "max_drawdown": res_c.max_drawdown, "n_trades": res_c.n_trades,
                }
                log.info("allocator.carry.done", sharpe=res_c.sharpe)
            except Exception as ex:
                log.exception("allocator.carry.failed", error=str(ex))

    if not engines_equity:
        raise HTTPException(400, "Nessun motore ha prodotto risultati validi nel periodo")

    # 4. F&G series
    fng_series = None
    if body.apply_fng_overlay:
        fng_rows = await sentiment_repo.fetch_fng(
            session, start=body.start_date, end=body.end_date, limit=20000, order="asc",
        )
        if fng_rows:
            df_fng = pd.DataFrame(
                [{"date": r.fng_date, "value": r.value} for r in fng_rows]
            ).set_index("date")
            df_fng["ema_24w"] = df_fng["value"].astype(float).ewm(span=168, adjust=False).mean()
            fng_series = df_fng["ema_24w"]
            fng_series.index = fng_series.index.tz_localize(None).tz_localize("UTC")

    # 5. Run allocator
    config_a = AllocatorConfig(
        rolling_sharpe_days=body.rolling_sharpe_days,
        rebalance_days=body.rebalance_days,
        initial_cash=body.initial_cash,
    )

    # Normalize indices: ensure all timezone-aware UTC
    for name, df in engines_equity.items():
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        engines_equity[name] = df

    log.info("allocator.combine", engines=list(engines_equity.keys()),
             fng_overlay=body.apply_fng_overlay)
    res = run_allocator(engines_equity, fng_series, None, config_a)

    return AllocatorResponse(
        start_date=res.start_date,
        end_date=res.end_date,
        initial_cash=res.initial_cash,
        final_equity=res.final_equity,
        total_return=res.total_return,
        sharpe=res.sharpe,
        sortino=res.sortino,
        max_drawdown=res.max_drawdown,
        correlation_matrix=res.correlation_matrix,
        per_engine_contribution={k: float(v) for k, v in res.per_engine_contribution.items()},
        per_engine_metrics=per_engine_metrics,
        equity_curve=[
            APO(
                t=p.t, equity=p.equity,
                weight_trend=p.weight_trend, weight_statarb=p.weight_statarb, weight_carry=p.weight_carry,
                fng_ema=p.fng_ema, regime=p.regime, gate_active=p.gate_active,
            ) for p in res.equity_curve
        ],
        config={
            "rolling_sharpe_days": config_a.rolling_sharpe_days,
            "rebalance_days": config_a.rebalance_days,
            "fng_overlay_applied": body.apply_fng_overlay,
            "engines_active": list(engines_equity.keys()),
        },
    )
