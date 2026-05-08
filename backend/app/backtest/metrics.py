"""Metriche risk-adjusted standard sul backtest.

Calcoliamo qui le metriche per avere controllo sui valori (Sharpe annualizzato
con freq corretta, no NaN spurio, ecc.) — vectorbt le calcola anch'esso ma
la freq mapping non è sempre corretta per crypto 24/7.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


# Numero di periodi per anno (crypto trading 24/7, 365 giorni)
PERIODS_PER_YEAR: dict[str, int] = {
    "1m": 525_600,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "4h": 2_190,
    "1d": 365,
}


@dataclass
class Metrics:
    """Output dei calcoli — tutti float, NaN safe (None se indefinito)."""

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

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "total_return": self.total_return,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "calmar": self.calmar,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "n_trades": self.n_trades,
            "avg_trade_pct": self.avg_trade_pct,
            "final_equity": self.final_equity,
        }


def compute_metrics(
    equity: pd.Series,
    trade_pnls: pd.Series | np.ndarray | list[float],
    timeframe: str,
    initial_cash: float,
) -> Metrics:
    """Calcola metriche risk-adjusted da equity curve + lista P&L per trade.

    Args:
        equity: serie temporale dell'equity (mark-to-market). Index timestamp.
        trade_pnls: P&L assoluto per trade (chiusi). Empty se 0 trades.
        timeframe: per annualizzazione (es. "4h" → 2190 periodi/anno).
        initial_cash: capitale iniziale (per total_return e profit_factor).

    Returns:
        Metrics con valori numerici. Sharpe/Calmar/etc. ``None`` se non
        calcolabili (es. 0 trades, std=0).
    """
    pnls = np.asarray(list(trade_pnls), dtype=float) if not isinstance(
        trade_pnls, np.ndarray
    ) else trade_pnls.astype(float)

    final_equity = float(equity.iloc[-1]) if len(equity) > 0 else float(initial_cash)
    total_return = (final_equity - initial_cash) / initial_cash if initial_cash > 0 else 0.0

    # Returns periodali (per Sharpe/Sortino)
    if len(equity) > 1:
        returns = equity.pct_change().dropna()
    else:
        returns = pd.Series(dtype=float)

    periods = PERIODS_PER_YEAR.get(timeframe, 365)

    sharpe = _sharpe_ratio(returns, periods)
    sortino = _sortino_ratio(returns, periods)
    max_dd = _max_drawdown(equity)
    calmar = _calmar_ratio(total_return, max_dd, equity, periods)

    n_trades = int(len(pnls))
    win_rate: float | None
    profit_factor: float | None
    avg_trade_pct: float | None

    if n_trades > 0:
        wins = pnls[pnls > 0]
        losses = pnls[pnls < 0]
        win_rate = float(len(wins) / n_trades) if n_trades > 0 else None
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(-losses.sum()) if len(losses) else 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        else:
            profit_factor = None  # nessuna perdita → infinito, lasciamo None
        avg_trade_pct = float(pnls.mean() / initial_cash) if initial_cash > 0 else None
    else:
        win_rate = None
        profit_factor = None
        avg_trade_pct = None

    return Metrics(
        total_return=float(total_return),
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=float(max_dd),
        win_rate=win_rate,
        profit_factor=profit_factor,
        n_trades=n_trades,
        avg_trade_pct=avg_trade_pct,
        final_equity=final_equity,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _sharpe_ratio(returns: pd.Series, periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None
    std = float(returns.std())
    if std == 0 or not math.isfinite(std):
        return None
    mean = float(returns.mean())
    return float((mean * periods_per_year) / (std * math.sqrt(periods_per_year)))


def _sortino_ratio(returns: pd.Series, periods_per_year: int) -> float | None:
    if len(returns) < 2:
        return None
    downside = returns[returns < 0]
    if len(downside) == 0:
        return None
    downside_std = float(downside.std())
    if downside_std == 0 or not math.isfinite(downside_std):
        return None
    mean = float(returns.mean())
    return float((mean * periods_per_year) / (downside_std * math.sqrt(periods_per_year)))


def _max_drawdown(equity: pd.Series) -> float:
    """Max drawdown come float negativo (-0.42 = -42%)."""
    if len(equity) == 0:
        return 0.0
    peak = equity.cummax()
    dd = (equity - peak) / peak
    min_dd = float(dd.min())
    return min_dd if math.isfinite(min_dd) else 0.0


def _calmar_ratio(
    total_return: float,
    max_dd: float,
    equity: pd.Series,
    periods_per_year: int,
) -> float | None:
    """Calmar = annualized return / |max drawdown|."""
    if max_dd == 0 or not math.isfinite(max_dd):
        return None
    n = len(equity)
    if n < 2:
        return None
    years = n / periods_per_year
    if years <= 0:
        return None
    annualized = (1 + total_return) ** (1 / years) - 1 if (1 + total_return) > 0 else -1.0
    return float(annualized / abs(max_dd))
