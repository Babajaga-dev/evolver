"""Fitness function multi-obiettivo per il GA.

Output: tuple di obiettivi che pymoo MINIMIZZA. Quindi:
    - F[0] = -Sharpe robusto (max Sharpe → min -Sharpe)
    - F[1] = |max drawdown peggiore| (min)

"Robusto" significa: media degli Sharpe su N finestre walk-forward meno una
penalty proporzionale alla loro deviazione standard, e SOLO finestre con
``n_trades >= MIN_TRADES_PER_WINDOW`` contribuiscono. Questo evita che
finestre con 1 trade producano Sharpe matematicamente validi ma
statisticamente nulli.

Penalty addizionale: se ``n_trades_total`` è sotto la soglia minima il
Sharpe robusto viene scontato proporzionalmente — strategie che sparano 2
trade in 9 mesi sono rumore, non strategie.

Note: complexity (terzo obiettivo originale) rimosso perché era costante
per tutti i cromosomi della stessa strategia → degenerava NSGA-II in
2-objective dichiarando 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.backtest.strategies import has_invalid_constraint
from app.backtest.walk_forward import WalkForwardResult, run_walk_forward


# Soglie per filtrare valutazioni statisticamente nulle
MIN_TRADES_PER_WINDOW = 5  # finestra valida se >= 5 trade
MIN_TRADES_TOTAL = 20  # totale GA-period valido se >= 20 trade


@dataclass(frozen=True)
class FitnessConfig:
    """Configurazione fitness — usata dal GA runner."""

    n_windows: int = 3  # walk-forward finestre durante GA
    initial_cash: float = 10_000.0
    fee: float = 0.001
    slippage_bps: float = 2.0
    sharpe_std_penalty: float = 0.5  # penalty su volatility dei Sharpe
    no_trade_sentinel: float = 100.0  # F[0] altissimo se cromosoma muto


@dataclass
class FitnessResult:
    """Output della fitness eval — sia obiettivi che metadata utili al monitor."""

    objectives: list[float]  # [neg_sharpe_robust, max_dd_abs]
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
    trade sufficienti, ritorna fitness "pessima" così pymoo lo elimina
    nelle generazioni successive.
    """
    cfg = config or FitnessConfig()

    # Estrai position_size_pct dal cromosoma per passarlo al backtest
    # engine. Resto del cromosoma → params della strategia.
    position_size_pct = float(chromosome_params.get("position_size_pct", 100.0))
    strategy_params = {
        k: v for k, v in chromosome_params.items() if k != "position_size_pct"
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
            position_size_pct=position_size_pct,
        )
    except (ValueError, KeyError):
        return _bad_fitness(cfg, sentinel_reason="walk_forward_failed")

    if wf.summary is None:  # pragma: no cover
        return _bad_fitness(cfg, sentinel_reason="no_summary")

    s = wf.summary

    # Filtra Sharpe SOLO da finestre con abbastanza trade — uno Sharpe da 1
    # trade non è uno Sharpe. Questo è IL fix che rompe la convergenza
    # spuria su nicchie low-signal.
    valid_windows = [
        w for w in wf.windows
        if w.sharpe is not None and w.n_trades >= MIN_TRADES_PER_WINDOW
    ]
    n_trades_total = sum(w.n_trades for w in wf.windows)

    # Strategia inattiva o low-signal → fitness pessima sentinel
    if not valid_windows or len(valid_windows) < cfg.n_windows / 2:
        return FitnessResult(
            objectives=[
                cfg.no_trade_sentinel,
                1.0,  # max_dd_abs assunto 100%
            ],
            sharpe_robust=-cfg.no_trade_sentinel,
            mean_max_drawdown=0.0,
            n_trades_total=n_trades_total,
            n_windows_winning=s.n_windows_winning,
            raw_walk_forward=wf,
        )

    # Sharpe robusto = mean - alpha * std (campionato sulle finestre valide)
    sharpes = [w.sharpe for w in valid_windows if w.sharpe is not None]
    mean_sharpe = sum(sharpes) / len(sharpes)
    std_sharpe = (
        (sum((x - mean_sharpe) ** 2 for x in sharpes) / len(sharpes)) ** 0.5
        if len(sharpes) > 1
        else 0.0
    )
    sharpe_robust = mean_sharpe - cfg.sharpe_std_penalty * std_sharpe

    # Penalty proporzionale: se n_trades_total < MIN_TRADES_TOTAL, scontiamo
    # lo Sharpe linearmente (fino a -50% se trade=0). 20 trades è la soglia
    # minima per credere alla statistica.
    if n_trades_total < MIN_TRADES_TOTAL:
        trade_factor = max(0.0, n_trades_total / MIN_TRADES_TOTAL)
        # Sharpe positivo: scontiamo verso 0; Sharpe negativo: ingrandiamo
        # (più punitivo). Trick: applichiamo factor solo se sharpe>0.
        if sharpe_robust > 0:
            sharpe_robust = sharpe_robust * trade_factor

    # MaxDD: peggiore tra le finestre. Nota: WindowResult.max_drawdown è
    # già negativo per convenzione vectorbt; abs() al positivo per l'obiettivo.
    max_dd_abs = abs(s.worst_max_drawdown)

    objectives = [
        -sharpe_robust,
        max_dd_abs,
    ]

    return FitnessResult(
        objectives=objectives,
        sharpe_robust=sharpe_robust,
        mean_max_drawdown=s.mean_max_drawdown,
        n_trades_total=n_trades_total,
        n_windows_winning=s.n_windows_winning,
        raw_walk_forward=wf,
    )


def _bad_fitness(cfg: FitnessConfig, sentinel_reason: str) -> FitnessResult:
    """Fitness "pessima" per cromosomi rotti — pymoo li eliminerà selezionando."""
    return FitnessResult(
        objectives=[cfg.no_trade_sentinel, 1.0],
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
