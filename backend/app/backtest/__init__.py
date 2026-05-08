"""Backtest engine — wrapper su vectorbt per simulazione strategie.

Filosofia:
    - vectorbt fa il lavoro pesante (vectorized P&L, equity, metrics)
    - noi wrappiamo per: API uniforme, validazione params, integrazione con
      indicators registry, output Pydantic-friendly
    - le strategie sono "famiglie" parametrizzate (cromosoma vincolato)
    - il GA della Fase 2 evolverà parametri di queste stesse strategie
"""

from app.backtest.engine import BacktestEngine, BacktestResult
from app.backtest.metrics import compute_metrics
from app.backtest.strategies import (
    STRATEGY_REGISTRY,
    StrategySpec,
    available_strategies,
    get_strategy,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "STRATEGY_REGISTRY",
    "StrategySpec",
    "available_strategies",
    "compute_metrics",
    "get_strategy",
]
