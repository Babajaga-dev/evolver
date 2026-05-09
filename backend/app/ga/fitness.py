"""Fitness function multi-obiettivo per il GA.

Output: tuple di obiettivi che pymoo MINIMIZZA. Quindi:
    - F[0] = -Sharpe robusto (max Sharpe → min -Sharpe)
    - F[1] = |max drawdown peggiore| (min)
    - F[2] = penalty di complessità / instability (min)

"Robusto" significa: media degli Sharpe su N finestre walk-forward meno una
penalty proporzionale alla loro deviazione standard. Premia strategie che
performano consistente nel tempo invece di brillanti su un singolo periodo.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.backtest.strategies import has_invalid_constraint
from app.backtest.walk_forward import WalkForwardResult, run_walk_forward


@dataclass(frozen=True)
class FitnessConfig:
    """Configurazione fitness — usata dal GA runner."""

    n_windows: int = 3  # walk-forward finestre durante GA (più di 5 sarebbe troppo lento)
    initial_cash: float = 10_000.0
    fee: float = 0.001
    slippage_bps: float = 2.0
    sharpe_std_penalty: float = 0.5  # penalty su volatility dei Sharpe
    no_trade_sentinel: float = 5.0  # F[0] alto se zero trade (segnale "skip me")


@dataclass
class FitnessResult:
    """Output della fitness eval — sia obiettivi che metadata utili al monitor."""

    objectives: list[float]  # [neg_sharpe_robust, max_dd_abs, complexity]
    sharpe_robust: float
    mean_max_drawdown: float
    n_trades_total: int
    n_windows_winning: int
    raw_walk_forward: WalkForwardResult


def compute_fitness(
    chromosome_params: dict[str, Any],
    *,
    df: pd.DataFrame,
    strategy_id: str,
    symbol: str,
    timeframe: str,
    config: FitnessConfig | None = None,
) -> FitnessResult:
    """Esegue walk-forward sul cromosoma e ritorna fitness.

    Robust to errors: se il backtest fallisce o la strategia non genera
    trade, ritorna fitness "pessima" così pymoo lo elimina nelle generazioni
    successive.
    """
    cfg = config or FitnessConfig()

    # Estraiamo il position_size dal cromosoma per applicarlo al sizing
    # (futuro: anche regime_filter_adx). Per ora lasciamo il backtest engine
    # con default sizing — useremo position_size_pct in slice futura.
    strategy_params = {
        k: v
        for k, v in chromosome_params.items()
        if k != "position_size_pct"
    }

    # Constraint check (es. fast < slow per ema_cross/macd_cross)
    if has_invalid_constraint(strategy_id, strategy_params):
        return _bad_fitness(cfg, sentinel_reason="invalid_constraint")

    try:
        wf = run_walk_forward(
            df=df,
            strategy_id=strategy_id,
            params=strategy_params,
            symbol=symbol,
            timeframe=timeframe,
            initial_cash=cfg.initial_cash,
            n_windows=cfg.n_windows,
            fee=cfg.fee,
            slippage_bps=cfg.slippage_bps,
        )
    except (ValueError, KeyError):
        # Cromosoma invalido o dati insufficienti → fitness pessima
        return _bad_fitness(cfg, sentinel_reason="walk_forward_failed")

    if wf.summary is None:  # pragma: no cover
        return _bad_fitness(cfg, sentinel_reason="no_summary")

    s = wf.summary

    # Sharpe robusto = mean - alpha * std
    sharpes = [w.sharpe for w in wf.windows if w.sharpe is not None]
    if not sharpes or s.n_windows_with_trades < cfg.n_windows / 2:
        # Strategia inattiva: penalty pesante per scoraggiare cromosomi muti
        return FitnessResult(
            objectives=[
                cfg.no_trade_sentinel,  # neg_sharpe alto = brutta
                1.0,  # max_dd_abs assunto 100%
                len(chromosome_params) / 10.0,
            ],
            sharpe_robust=-cfg.no_trade_sentinel,
            mean_max_drawdown=0.0,
            n_trades_total=sum(w.n_trades for w in wf.windows),
            n_windows_winning=s.n_windows_winning,
            raw_walk_forward=wf,
        )

    mean_sharpe = sum(sharpes) / len(sharpes)
    std_sharpe = (
        (sum((x - mean_sharpe) ** 2 for x in sharpes) / len(sharpes)) ** 0.5
        if len(sharpes) > 1
        else 0.0
    )
    sharpe_robust = mean_sharpe - cfg.sharpe_std_penalty * std_sharpe

    # MaxDD: usiamo il peggiore tra le finestre (penalizziamo il worst case)
    max_dd_abs = abs(s.worst_max_drawdown)

    # Complessità: per ora costante (la slice 2.1 introdurrà n_active_indicators)
    complexity = len(chromosome_params) / 10.0

    objectives = [
        -sharpe_robust,
        max_dd_abs,
        complexity,
    ]

    return FitnessResult(
        objectives=objectives,
        sharpe_robust=sharpe_robust,
        mean_max_drawdown=s.mean_max_drawdown,
        n_trades_total=sum(w.n_trades for w in wf.windows),
        n_windows_winning=s.n_windows_winning,
        raw_walk_forward=wf,
    )


def _bad_fitness(cfg: FitnessConfig, sentinel_reason: str) -> FitnessResult:
    """Fitness "pessima" per cromosomi rotti — pymoo li eliminerà selezionando."""
    return FitnessResult(
        objectives=[cfg.no_trade_sentinel, 1.0, 1.0],
        sharpe_robust=-cfg.no_trade_sentinel,
        mean_max_drawdown=0.0,
        n_trades_total=0,
        n_windows_winning=0,
        raw_walk_forward=WalkForwardResult(
            symbol="",
            timeframe="",
            strategy_id="",
            strategy_label=sentinel_reason,
            params={},
            initial_cash=cfg.initial_cash,
            n_windows=0,
            period_start=pd.Timestamp.utcnow().to_pydatetime(),
            period_end=pd.Timestamp.utcnow().to_pydatetime(),
            windows=[],
            summary=None,
        ),
    )
