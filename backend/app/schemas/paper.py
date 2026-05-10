"""Schemi Pydantic per /api/v1/paper/* — paper trading dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PaperStateResponse(BaseModel):
    portfolio_id: str
    initial_balance: float
    balance_quote: float
    holdings: dict[str, Any]
    equity: float
    drawdown_from_peak: float
    open_positions_count: int
    last_snapshot_at: str | None = None
    total_return_pct: float
    trades_total: int
    trades_open: int
    trades_closed: int
    trades_winning: int
    win_rate: float
    total_pnl: float
    status: str


class PaperTradeOut(BaseModel):
    id: uuid.UUID
    strategy_id: uuid.UUID | None = None
    symbol: str
    timeframe: str
    side: str
    status: str
    quantity: float
    entry_price: float
    exit_price: float | None = None
    entry_time: datetime
    exit_time: datetime | None = None
    fees: float
    pnl: float | None = None
    pnl_pct: float | None = None


class PaperTradesResponse(BaseModel):
    trades: list[PaperTradeOut]
    count: int


class EquityPoint(BaseModel):
    timestamp: datetime
    equity: float
    balance_quote: float
    drawdown_from_peak: float
    open_positions_count: int


class EquityCurveResponse(BaseModel):
    portfolio_id: str
    points: list[EquityPoint]
    count: int


class PaperSnapshotResponse(BaseModel):
    portfolio_id: str
    snapshot_at: datetime
    equity: float
    message: str
