"""Walk-forward analysis: backtest la stessa strategia su N finestre rolling.

Filosofia:
    Un singolo backtest su 1 anno è un sample di dimensione 1. Una strategia
    può sembrare brillante per fortuna sui dati specifici. Walk-forward divide
    il periodo in N sub-finestre e ri-esegue il backtest su ognuna,
    permettendo di stimare:
        - performance media (centro)
        - volatility della performance (varianza)
        - count di finestre vincenti vs perdenti (frazione)
    Una strategia "robusta" performa decentemente in *molte* finestre, non
    solo in una.

In v1 le finestre non si sovrappongono ed eseguiamo lo stesso set di
parametri ovunque (no parameter optimization per finestra). La fase 2 GA
introdurrà la versione completa training+validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, pstdev
from typing import Any

import pandas as pd

from app.backtest.engine import BacktestEngine, BacktestResult


@dataclass
class WindowResult:
    """Risultato del backtest su una singola finestra."""

    window_index: int
    window_start: datetime
    window_end: datetime
    n_candles: int
    n_trades: int
    total_return: float
    sharpe: float | None
    calmar: float | None
    max_drawdown: float
    win_rate: float | None
    final_equity: float


@dataclass
class WalkForwardSummary:
    """Stats aggregate su tutte le finestre."""

    n_windows: int
    n_windows_winning: int  # Sharpe > 0 OR total_return > 0
    n_windows_with_trades: int
    mean_total_return: float
    std_total_return: float
    mean_sharpe: float | None
    std_sharpe: float | None
    mean_max_drawdown: float
    worst_max_drawdown: float
    best_total_return: float
    worst_total_return: float
    verdict: str  # "robust" | "mixed" | "unstable" | "no_signal"
    verdict_reason: str


@dataclass
class WalkForwardResult:
    """Risultato completo della walk-forward analysis."""

    symbol: str
    timeframe: str
    strategy_id: str
    strategy_label: str
    params: dict[str, Any]
    initial_cash: float
    n_windows: int
    period_start: datetime
    period_end: datetime
    windows: list[WindowResult] = field(default_factory=list)
    summary: WalkForwardSummary | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def run_walk_forward(
    df: pd.DataFrame,
    *,
    strategy_id: str,
    params: dict[str, Any],
    symbol: str,
    timeframe: str,
    initial_cash: float = 10_000.0,
    n_windows: int = 5,
    fee: float = 0.001,
    slippage_bps: float = 2.0,
) -> WalkForwardResult:
    """Esegue walk-forward: divide df in n_windows finestre sequenziali
    contigue (no overlap) ed esegue ``BacktestEngine`` su ognuna.

    Note:
        - Le finestre sono di pari lunghezza (eccetto l'ultima che assorbe
          il resto della divisione).
        - ``initial_cash`` viene resettato per ogni finestra (no compounding
          tra finestre).
        - Servono almeno ``50 * n_windows`` candele per evitare finestre
          troppo corte.

    Returns:
        WalkForwardResult con lista di WindowResult + summary.
    """
    if n_windows < 2:
        raise ValueError("n_windows must be >= 2")
    if df.empty:
        raise ValueError("DataFrame vuoto: impossibile fare walk-forward")

    n = len(df)
    if n < 50 * n_windows:
        raise ValueError(
            f"Dati insufficienti per {n_windows} finestre: "
            f"servono almeno {50 * n_windows} candele, ne hai {n}"
        )

    engine = BacktestEngine(fee=fee, slippage_bps=slippage_bps)

    window_size = n // n_windows
    windows: list[WindowResult] = []

    for i in range(n_windows):
        start_idx = i * window_size
        # L'ultima finestra prende il resto
        end_idx = n if i == n_windows - 1 else (i + 1) * window_size
        window_df = df.iloc[start_idx:end_idx]

        # Skip se troppo corta (paranoia)
        if len(window_df) < 50:
            continue

        try:
            res: BacktestResult = engine.run(
                df=window_df,
                strategy_id=strategy_id,
                params=params,
                symbol=symbol,
                timeframe=timeframe,
                initial_cash=initial_cash,
            )
        except Exception:  # pragma: no cover
            # Se qualche finestra fallisce, registriamo come 0 trade
            res = None  # type: ignore[assignment]

        if res is None:
            windows.append(
                WindowResult(
                    window_index=i,
                    window_start=window_df.index[0].to_pydatetime(),
                    window_end=window_df.index[-1].to_pydatetime(),
                    n_candles=len(window_df),
                    n_trades=0,
                    total_return=0.0,
                    sharpe=None,
                    calmar=None,
                    max_drawdown=0.0,
                    win_rate=None,
                    final_equity=initial_cash,
                )
            )
        else:
            m = res.metrics
            windows.append(
                WindowResult(
                    window_index=i,
                    window_start=res.start,
                    window_end=res.end,
                    n_candles=len(window_df),
                    n_trades=m.n_trades,
                    total_return=m.total_return,
                    sharpe=m.sharpe,
                    calmar=m.calmar,
                    max_drawdown=m.max_drawdown,
                    win_rate=m.win_rate,
                    final_equity=m.final_equity,
                )
            )

    summary = _compute_summary(windows)

    return WalkForwardResult(
        symbol=symbol,
        timeframe=timeframe,
        strategy_id=strategy_id,
        strategy_label=strategy_id,  # caller può patchare
        params=params,
        initial_cash=initial_cash,
        n_windows=n_windows,
        period_start=df.index[0].to_pydatetime(),
        period_end=df.index[-1].to_pydatetime(),
        windows=windows,
        summary=summary,
    )


def _compute_summary(windows: list[WindowResult]) -> WalkForwardSummary:
    """Aggregate stats + verdict di robustezza."""
    n = len(windows)
    if n == 0:
        return WalkForwardSummary(
            n_windows=0,
            n_windows_winning=0,
            n_windows_with_trades=0,
            mean_total_return=0.0,
            std_total_return=0.0,
            mean_sharpe=None,
            std_sharpe=None,
            mean_max_drawdown=0.0,
            worst_max_drawdown=0.0,
            best_total_return=0.0,
            worst_total_return=0.0,
            verdict="no_signal",
            verdict_reason="Nessuna finestra valida",
        )

    returns = [w.total_return for w in windows]
    mdds = [w.max_drawdown for w in windows]
    sharpes = [w.sharpe for w in windows if w.sharpe is not None]

    n_with_trades = sum(1 for w in windows if w.n_trades > 0)
    n_winning = sum(1 for w in windows if w.total_return > 0)

    mean_ret = mean(returns)
    std_ret = pstdev(returns) if n > 1 else 0.0

    mean_sh = mean(sharpes) if sharpes else None
    std_sh = pstdev(sharpes) if len(sharpes) > 1 else None

    verdict, reason = _verdict(
        n_windows=n,
        n_winning=n_winning,
        n_with_trades=n_with_trades,
        mean_return=mean_ret,
        mean_sharpe=mean_sh,
    )

    return WalkForwardSummary(
        n_windows=n,
        n_windows_winning=n_winning,
        n_windows_with_trades=n_with_trades,
        mean_total_return=mean_ret,
        std_total_return=std_ret,
        mean_sharpe=mean_sh,
        std_sharpe=std_sh,
        mean_max_drawdown=mean(mdds),
        worst_max_drawdown=min(mdds),
        best_total_return=max(returns),
        worst_total_return=min(returns),
        verdict=verdict,
        verdict_reason=reason,
    )


def _verdict(
    *,
    n_windows: int,
    n_winning: int,
    n_with_trades: int,
    mean_return: float,
    mean_sharpe: float | None,
) -> tuple[str, str]:
    """Logic del verdict di robustezza.

    Regole:
        - "no_signal": meno della metà delle finestre ha generato trade
        - "robust": ≥80% finestre vincenti AND mean_return > 0
                    AND (mean_sharpe is None OR mean_sharpe > 0.3)
        - "mixed": 40-79% finestre vincenti
        - "unstable": <40% finestre vincenti
    """
    if n_with_trades < n_windows * 0.5:
        return (
            "no_signal",
            f"Solo {n_with_trades}/{n_windows} finestre con trade: "
            f"strategia non genera segnali in maniera consistente",
        )

    win_pct = n_winning / n_windows

    if win_pct >= 0.8 and mean_return > 0 and (mean_sharpe is None or mean_sharpe > 0.3):
        sharpe_str = f"{mean_sharpe:.2f}" if mean_sharpe is not None else "n/a"
        return (
            "robust",
            f"{n_winning}/{n_windows} finestre vincenti, "
            f"mean return {mean_return:+.2%}, "
            f"mean Sharpe {sharpe_str}",
        )

    if win_pct >= 0.4:
        return (
            "mixed",
            f"{n_winning}/{n_windows} finestre vincenti — performance "
            f"non consistente, mean return {mean_return:+.2%}",
        )

    return (
        "unstable",
        f"Solo {n_winning}/{n_windows} finestre vincenti — strategia "
        f"perde nella maggioranza dei sub-periodi",
    )
