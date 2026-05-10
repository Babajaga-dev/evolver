"""Schemi Pydantic per /api/v1/oos."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OosValidateRequest(BaseModel):
    population_id: str = Field(description="GA run completato da validare")
    test_days: int = Field(default=90, ge=7, le=730)
    top_k: int = Field(default=10, ge=1, le=50)
    initial_cash: float = Field(default=10_000.0, gt=0)


class OosStrategyOut(BaseModel):
    rank: int
    chromosome: dict[str, Any]
    sharpe_train: float
    max_drawdown_train: float
    n_trades_train: int
    sharpe_test: float | None
    total_return_test: float
    max_drawdown_test: float
    n_trades_test: int
    win_rate_test: float | None
    final_equity_test: float
    degradation_pct: float | None
    verdict: str
    verdict_reason: str


class OosEvolutionPointOut(BaseModel):
    generation: int
    best_sharpe_robust_train: float
    mean_sharpe_robust_train: float
    diversity: float
    best_sharpe_test: float | None
    best_total_return_test: float
    best_n_trades_test: int


class OosResultResponse(BaseModel):
    population_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    test_days: int
    top_k: int
    initial_cash: float
    strategies: list[OosStrategyOut]
    evolution_curve: list[OosEvolutionPointOut]
    overall_verdict: str
    overall_reason: str
    n_robust: int
    n_mixed: int
    n_overfit: int
    n_no_signal: int
