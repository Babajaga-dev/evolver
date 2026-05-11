"""Schemi Pydantic per /api/v1/carry."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class CarryRunRequest(BaseModel):
    symbol: str = Field(default="BTC/USDT")
    start_date: datetime
    end_date: datetime
    timeframe: str = Field(default="4h", description="4h o 8h consigliato (allinea funding 8h)")
    initial_cash: float = Field(default=10_000.0, gt=0)
    fee_taker: float = Field(default=0.0004, ge=0, le=0.01)
    slippage_bps: float = Field(default=2.0, ge=0, le=50)
    entry_threshold: float = Field(default=0.0001, ge=0, le=0.01)
    exit_threshold: float = Field(default=0.00005, ge=0, le=0.01)
    consecutive_entry: int = Field(default=3, ge=1, le=30)
    consecutive_exit: int = Field(default=3, ge=1, le=30)
    position_fraction: float = Field(default=0.5, gt=0, le=1.0)
    max_drawdown_pct: float = Field(default=-0.05, le=0, ge=-1.0)


class CarryEquityPoint(BaseModel):
    t: str
    equity: float
    in_position: bool
    funding_rate: float


class CarryTradeOut(BaseModel):
    entry_time: str | None
    exit_time: str | None
    entry_price: float
    exit_price: float | None
    notional: float
    funding_collected: float
    n_funding_periods: int
    fees_paid: float
    pnl: float
    pnl_pct: float


class CarryResponse(BaseModel):
    symbol: str
    start_date: datetime
    end_date: datetime
    n_funding_periods: int
    n_trades: int
    total_funding_collected: float
    total_fees_paid: float
    final_equity: float
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    apr: float
    equity_curve: list[CarryEquityPoint]
    trades: list[CarryTradeOut]
