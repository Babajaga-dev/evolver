"""Schemi Pydantic per request/response del backtest engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    symbol: str = Field(description="Symbol es. 'BTC/USDT'")
    timeframe: str = Field(description="Timeframe es. '4h'")
    strategy_id: str = Field(description="ID strategia dal registry")
    params: dict[str, Any] = Field(default_factory=dict)
    period_days: int = Field(
        default=365,
        ge=7,
        le=365 * 10,
        description="Quanti giorni di storico usare (a ritroso da oggi)",
    )
    initial_cash: float = Field(default=10_000.0, gt=0)


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class StrategyParamInfo(BaseModel):
    name: str
    type: str
    default: Any
    min: float | int | None = None
    max: float | int | None = None
    description: str = ""


class StrategyInfo(BaseModel):
    id: str
    label: str
    family: str
    description: str
    params: list[StrategyParamInfo]


class StrategiesRegistryResponse(BaseModel):
    strategies: list[StrategyInfo]


class TradeRecordOut(BaseModel):
    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    size: float
    direction: str
    pnl: float
    pnl_pct: float


class EquityPointOut(BaseModel):
    timestamp: datetime
    equity: float
    drawdown: float


class MetricsOut(BaseModel):
    total_return: float
    sharpe: float | None
    sortino: float | None
    calmar: float | None
    max_drawdown: float
    win_rate: float | None
    profit_factor: float | None
    n_trades: int
    avg_trade_pct: float | None
    final_equity: float


class BacktestResponse(BaseModel):
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_label: str
    params: dict[str, Any]
    initial_cash: float
    fee: float
    slippage: float
    start: datetime
    end: datetime
    equity_curve: list[EquityPointOut]
    trades: list[TradeRecordOut]
    metrics: MetricsOut
