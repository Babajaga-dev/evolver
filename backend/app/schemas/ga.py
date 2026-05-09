"""Schemi Pydantic per il GA."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class GaRunRequest(BaseModel):
    strategy_id: str = Field(description="ID strategia dal registry")
    symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="4h")
    period_days: int = Field(default=365, ge=90, le=365 * 5)
    initial_cash: float = Field(default=10_000.0, gt=0)
    population_size: int = Field(default=30, ge=10, le=200)
    # n_generations >= 5: con <5 il GA è praticamente solo random sampling
    n_generations: int = Field(default=15, ge=5, le=200)
    # n_windows >= 4: per uno std robusto su sharpes
    n_windows: int = Field(default=4, ge=4, le=10)
    seed: int = Field(default=42, ge=0)


# ---------------------------------------------------------------------------
# Response — stato run
# ---------------------------------------------------------------------------


class GenerationSnapshotOut(BaseModel):
    generation: int
    best_fitness: float
    mean_fitness: float
    worst_fitness: float
    std_fitness: float
    best_sharpe_robust: float
    best_max_dd: float
    diversity: float
    elapsed_seconds: float


class StrategySnapshotOut(BaseModel):
    chromosome: dict[str, Any]
    sharpe_robust: float
    max_drawdown_abs: float
    complexity: float
    n_trades: int
    n_windows_winning: int
    generation: int


class GaRunStatus(BaseModel):
    population_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    status: str  # "pending" | "running" | "completed" | "failed"
    current_generation: int
    total_generations: int
    population_size: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    elapsed_seconds: float
    error: str | None = None
    generations: list[GenerationSnapshotOut]
    pareto_front: list[StrategySnapshotOut]
    top_strategies: list[StrategySnapshotOut]


class GaRunCreated(BaseModel):
    population_id: str
    status: str
    message: str = "Run avviato in background. Polla GET /api/v1/ga/runs/{id} per progress."


class GaRunSummary(BaseModel):
    """Lista runs (snapshot ridotto)."""

    population_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    status: str
    current_generation: int
    total_generations: int
    started_at: datetime | None
    best_sharpe_robust: float | None


class GaRunsListResponse(BaseModel):
    runs: list[GaRunSummary]
