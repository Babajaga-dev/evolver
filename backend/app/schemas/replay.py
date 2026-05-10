"""Schemi Pydantic per /api/v1/replay."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReplayStartRequest(BaseModel):
    name: str = Field(default="Replay")
    symbol: str = Field(default="BTC/USDT")
    start_date: datetime
    end_date: datetime
    initial_cash: float = Field(default=10_000.0, gt=0)
    retrain_cadence_days: int = Field(default=14, ge=1, le=365)
    lookback_days: int = Field(default=180, ge=30, le=1825)
    kill_switch_dd_pct: float = Field(default=-10.0, le=0, ge=-50)
    kill_switch_window_days: int = Field(default=30, ge=7, le=180)
    ga_pop_size: int = Field(default=20, ge=10, le=80)
    ga_generations: int = Field(default=8, ge=5, le=40)


class ReplayRunSummary(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    symbol: str
    current_simulated_date: datetime | None
    current_equity: float
    progress_pct: float
    n_retrains: int
    n_kill_switch_events: int
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime
    final_metrics: dict[str, Any] | None
    config: dict[str, Any]


class ReplayEquityPointOut(BaseModel):
    t: datetime
    equity: float
    position_size_pct: float
    drawdown_pct: float
    regime: str | None
    n_trades_so_far: int


class ReplayRetrainEventOut(BaseModel):
    t: datetime
    trigger: str
    organism: dict[str, Any]
    elapsed_seconds: float
    equity_at_retrain: float


class ReplayDetailResponse(BaseModel):
    summary: ReplayRunSummary
    equity_curve: list[ReplayEquityPointOut]
    retrain_events: list[ReplayRetrainEventOut]


class ReplayListResponse(BaseModel):
    runs: list[ReplayRunSummary]


class AdminBackfillRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h", "1d"])
    start_date: datetime
    end_date: datetime | None = None


class AdminBackfillResponse(BaseModel):
    started: bool
    job_id: str
    message: str
