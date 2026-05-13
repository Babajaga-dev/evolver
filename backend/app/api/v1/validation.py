"""Endpoint /api/v1/validation/* — Walk-forward double-OOS + bootstrap.

Ref: arXiv 2602.10785 (Feb 2026) — train su BTC params, apply unseen asset + window.
"""
from __future__ import annotations
from datetime import datetime
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.repositories import ohlcv as ohlcv_repo
from app.trend.engine import TrendConfig, run_trend_backtest
from app.validation.runner import (
    BootstrapResult,
    DoubleOOSResult,
    WindowResult,
    assess_verdict,
    bootstrap_sub_windows,
)
from app.metrics.deflated_sharpe import deflated_sharpe_ratio

router = APIRouter(prefix="/validation", tags=["validation"])
log = get_logger(__name__)


class ValidationRequest(BaseModel):
    train_asset: str = "BTC/USDT"
    test_assets: list[str] = Field(
        default_factory=lambda: ["ETH/USDT", "SOL/USDT", "BNB/USDT"],
        description="Asset NEVER seen during training, for double-OOS",
    )
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    timeframe: str = "1d"
    fee_mode: str = "retail"
    universe_rolling: bool = False
    top_n_assets: int = 5
    bootstrap_samples: int = 30
    bootstrap_sub_window_days: int = 180


class WindowResultOut(BaseModel):
    label: str
    asset: str
    start: datetime | None
    end: datetime | None
    sharpe: float
    return_pct: float
    max_drawdown: float
    n_trades: int
    dsr: dict


class BootstrapOut(BaseModel):
    n_samples: int
    sharpe_mean: float
    sharpe_std: float
    sharpe_p5: float
    sharpe_p50: float
    sharpe_p95: float
    return_mean: float
    pct_positive_windows: float


class ValidationResponse(BaseModel):
    train: WindowResultOut
    single_oos: WindowResultOut
    double_oos: list[WindowResultOut]
    bootstrap: BootstrapOut
    verdict: str
    explanation: str
    fee_mode: str


def _ohlcv_df(rows) -> pd.DataFrame:
    return pd.DataFrame(
        [{"timestamp": r.timestamp, "open": float(r.open), "high": float(r.high),
          "low": float(r.low), "close": float(r.close), "volume": float(r.volume)} for r in rows]
    ).set_index("timestamp").sort_index()


async def _fetch_ohlcv(session: AsyncSession, sym: str, tf: str, start: datetime, end: datetime) -> pd.DataFrame:
    rows = await ohlcv_repo.fetch_ohlcv(
        session, symbol=sym, timeframe=tf, start=start, end=end, limit=200_000, order="asc",
    )
    if not rows:
        return pd.DataFrame()
    return _ohlcv_df(rows)


def _run_trend(ohlcv_by_sym: dict[str, pd.DataFrame], body: ValidationRequest) -> dict:
    """Run TREND backtest and return summary dict."""
    cfg = TrendConfig(
        symbols=list(ohlcv_by_sym.keys()),
        timeframe=body.timeframe,
        top_n_assets=min(body.top_n_assets, len(ohlcv_by_sym)),
        fee_mode=body.fee_mode,
        universe_rolling=body.universe_rolling,
        initial_cash=10_000.0,
    )
    res = run_trend_backtest(ohlcv_by_sym, cfg)
    return {
        "start_date": res.start_date,
        "end_date": res.end_date,
        "sharpe": res.sharpe,
        "total_return": res.total_return,
        "max_drawdown": res.max_drawdown,
        "n_trades": res.n_trades,
        "equity_curve": res.equity_curve,
    }


@router.post("/double-oos", response_model=ValidationResponse)
async def run_double_oos(
    body: ValidationRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ValidationResponse:
    """Walk-forward double-OOS validation completo.

    1. Train: TREND su train_asset nel train_period
    2. Single OOS: TREND su train_asset nel test_period
    3. Double OOS: TREND su ciascun test_asset nel test_period
    4. Bootstrap: 30 sub-finestre random nel test_period
    5. Verdict onesto basato su DSR + cross-checks
    """
    # 1. TRAIN
    df_train = await _fetch_ohlcv(session, body.train_asset, body.timeframe, body.train_start, body.train_end)
    if df_train.empty or len(df_train) < 60:
        raise HTTPException(400, f"Dati insufficienti per training {body.train_asset} nel periodo")
    log.info("validation.train", asset=body.train_asset, n_bars=len(df_train))
    train_res = _run_trend({body.train_asset: df_train}, body)
    train_returns = pd.Series([p["equity"] for p in train_res["equity_curve"]]).pct_change().dropna().values
    train_dsr = deflated_sharpe_ratio(
        observed_sharpe=train_res["sharpe"],
        returns=train_returns,
        n_trials=10,
    )

    # 2. SINGLE OOS — same asset, future period
    df_single = await _fetch_ohlcv(session, body.train_asset, body.timeframe, body.test_start, body.test_end)
    if df_single.empty or len(df_single) < 60:
        raise HTTPException(400, f"Dati insufficienti per single OOS {body.train_asset}")
    single_res = _run_trend({body.train_asset: df_single}, body)
    single_returns = pd.Series([p["equity"] for p in single_res["equity_curve"]]).pct_change().dropna().values
    single_dsr = deflated_sharpe_ratio(observed_sharpe=single_res["sharpe"], returns=single_returns, n_trials=10)

    # 3. DOUBLE OOS — different assets, future period
    double_results = []
    double_sharpes = []
    for asset in body.test_assets:
        df_d = await _fetch_ohlcv(session, asset, body.timeframe, body.test_start, body.test_end)
        if df_d.empty or len(df_d) < 60:
            log.warning("validation.double.skip", asset=asset, n_rows=len(df_d))
            continue
        try:
            d_res = _run_trend({asset: df_d}, body)
            d_returns = pd.Series([p["equity"] for p in d_res["equity_curve"]]).pct_change().dropna().values
            d_dsr = deflated_sharpe_ratio(observed_sharpe=d_res["sharpe"], returns=d_returns, n_trials=10)
            double_results.append({
                "label": "double_oos",
                "asset": asset,
                "res": d_res,
                "dsr": d_dsr,
            })
            double_sharpes.append(d_res["sharpe"])
        except Exception as ex:
            log.exception("validation.double.error", asset=asset, error=str(ex))

    # 4. BOOTSTRAP — N sub-windows random nel test period su single_oos asset
    bootstrap = bootstrap_sub_windows(
        ohlcv_by_sym={body.train_asset: df_single},
        config_template={
            "symbols": [body.train_asset],
            "timeframe": body.timeframe,
            "top_n_assets": 1,
            "fee_mode": body.fee_mode,
            "initial_cash": 10_000.0,
        },
        full_start=body.test_start,
        full_end=body.test_end,
        n_samples=body.bootstrap_samples,
        sub_window_days=body.bootstrap_sub_window_days,
    )

    # 5. VERDICT
    verdict, explanation = assess_verdict(
        train_sharpe=train_res["sharpe"],
        single_oos_sharpe=single_res["sharpe"],
        double_oos_sharpes=double_sharpes,
        bootstrap_p5=bootstrap.sharpe_p5,
        train_dsr=train_dsr["dsr"],
    )

    return ValidationResponse(
        train=WindowResultOut(
            label="train", asset=body.train_asset,
            start=train_res["start_date"], end=train_res["end_date"],
            sharpe=train_res["sharpe"], return_pct=train_res["total_return"]*100,
            max_drawdown=train_res["max_drawdown"]*100, n_trades=train_res["n_trades"],
            dsr=train_dsr,
        ),
        single_oos=WindowResultOut(
            label="single_oos", asset=body.train_asset,
            start=single_res["start_date"], end=single_res["end_date"],
            sharpe=single_res["sharpe"], return_pct=single_res["total_return"]*100,
            max_drawdown=single_res["max_drawdown"]*100, n_trades=single_res["n_trades"],
            dsr=single_dsr,
        ),
        double_oos=[
            WindowResultOut(
                label="double_oos", asset=d["asset"],
                start=d["res"]["start_date"], end=d["res"]["end_date"],
                sharpe=d["res"]["sharpe"], return_pct=d["res"]["total_return"]*100,
                max_drawdown=d["res"]["max_drawdown"]*100, n_trades=d["res"]["n_trades"],
                dsr=d["dsr"],
            ) for d in double_results
        ],
        bootstrap=BootstrapOut(
            n_samples=bootstrap.n_samples,
            sharpe_mean=bootstrap.sharpe_mean,
            sharpe_std=bootstrap.sharpe_std,
            sharpe_p5=bootstrap.sharpe_p5,
            sharpe_p50=bootstrap.sharpe_p50,
            sharpe_p95=bootstrap.sharpe_p95,
            return_mean=bootstrap.return_mean,
            pct_positive_windows=bootstrap.pct_positive_windows,
        ),
        verdict=verdict,
        explanation=explanation,
        fee_mode=body.fee_mode,
    )
