"""Schemi Pydantic per TREND backtest endpoint."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class TrendRunRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframe: str = "4h"
    start_date: datetime
    end_date: datetime
    initial_cash: float = Field(default=10_000.0, gt=0)
    lookbacks: list[int] = Field(default_factory=lambda: [5, 10, 20, 30, 60, 90, 150, 250])
    target_vol_annual: float = Field(default=0.40, gt=0, le=2.0)
    trailing_stop_atr_mult: float = Field(default=3.0, gt=0, le=10.0)
    rebalance_days: int = Field(default=30, ge=1, le=365)
    top_n_assets: int = Field(default=10, ge=1, le=50)
    long_weight: float = Field(default=0.70, ge=0, le=1.0)
    short_weight: float = Field(default=0.30, ge=0, le=1.0)
    fee_bps: float = Field(default=4.0, ge=0, le=50)
    slippage_bps: float = Field(default=2.0, ge=0, le=50)


class TrendEquityPoint(BaseModel):
    t: datetime
    equity: float
    exposure_pct: float
    n_positions: int


class TrendTradeOut(BaseModel):
    symbol: str
    side: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    pnl: float
    pnl_pct: float
    holding_days: float
    reason: str


class TrendMonthlyReturn(BaseModel):
    month: str
    return_pct: float
    n_trades: int


class TrendAssetStat(BaseModel):
    symbol: str
    n_trades: int
    n_winners: int
    total_pnl: float
    avg_pnl_pct: float


class TrendResponse(BaseModel):
    symbols: list[str]
    timeframe: str
    start_date: datetime
    end_date: datetime
    n_trades: int
    n_long_trades: int
    n_short_trades: int
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    avg_pnl_pct: float
    monthly_returns: list[TrendMonthlyReturn]
    equity_curve: list[TrendEquityPoint]
    trades: list[TrendTradeOut]
    per_asset_stats: list[TrendAssetStat]
    baselines: dict
