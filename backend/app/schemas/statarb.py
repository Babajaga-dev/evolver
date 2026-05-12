"""Schemi Pydantic per STAT-ARB pairs trade."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class StatArbRunRequest(BaseModel):
    symbol_a: str = "BTC/USDT"
    symbol_b: str = "ETH/USDT"
    timeframe: str = "4h"
    start_date: datetime
    end_date: datetime
    initial_cash: float = Field(default=10_000.0, gt=0)
    lookback_bars: int = Field(default=180, ge=30, le=1000)
    z_entry: float = Field(default=2.0, ge=0.5, le=5.0)
    z_exit: float = Field(default=0.5, ge=0.0, le=2.0)
    z_stop: float = Field(default=3.5, ge=2.0, le=10.0)
    max_half_life_bars: int = Field(default=180, ge=10, le=2000)
    capital_per_trade: float = Field(default=0.50, gt=0, le=1.0)
    fee_bps: float = Field(default=4.0, ge=0, le=50)
    slippage_bps: float = Field(default=2.0, ge=0, le=50)


class StatArbEquityPointOut(BaseModel):
    t: datetime
    equity: float
    spread: float
    zscore: float
    hedge_ratio: float
    position: int


class StatArbTradeOut(BaseModel):
    entry_time: datetime
    exit_time: datetime
    side: str
    entry_spread: float
    exit_spread: float
    entry_z: float
    exit_z: float
    qty_a: float
    qty_b: float
    pnl: float
    pnl_pct: float
    holding_bars: int
    reason: str


class StatArbMonthlyReturn(BaseModel):
    month: str
    return_pct: float
    n_trades: int


class StatArbResponse(BaseModel):
    symbol_a: str
    symbol_b: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    n_trades: int
    n_winners: int
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    avg_holding_bars: float
    beta_vs_btc: float
    avg_hedge_ratio: float
    cointegration_p_value: float
    equity_curve: list[StatArbEquityPointOut]
    trades: list[StatArbTradeOut]
    monthly_returns: list[StatArbMonthlyReturn]
