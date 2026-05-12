"""Schemi Pydantic per Risk Allocator."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class AllocatorRunRequest(BaseModel):
    symbols: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    timeframe: str = "4h"
    start_date: datetime
    end_date: datetime
    initial_cash: float = 30000.0
    rolling_sharpe_days: int = 30
    rebalance_days: int = 7
    apply_fng_overlay: bool = True
    apply_gate_overlay: bool = True
    # Engine configs (will run each individually)
    run_trend: bool = True
    run_statarb: bool = True
    run_carry: bool = True
    # StatArb pair (defaults to first two symbols)
    statarb_symbol_a: str = "BTC/USDT"
    statarb_symbol_b: str = "ETH/USDT"


class AllocatorPointOut(BaseModel):
    t: datetime
    equity: float
    weight_trend: float
    weight_statarb: float
    weight_carry: float
    fng_ema: float | None
    regime: str
    gate_active: bool


class AllocatorResponse(BaseModel):
    start_date: datetime
    end_date: datetime
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    correlation_matrix: dict
    per_engine_contribution: dict
    per_engine_metrics: dict  # {engine_name: {sharpe, return, dd, n_trades}}
    equity_curve: list[AllocatorPointOut]
    config: dict
