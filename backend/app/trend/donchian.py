"""Donchian channel ensemble multi-lookback.

Per ogni lookback L:
- upper_L = max(high) negli ultimi L periodi
- lower_L = min(low) negli ultimi L periodi
- signal: +1 se close > upper_L (LONG breakout), -1 se close < lower_L (SHORT breakout)

L'ensemble somma i segnali di tutti i lookback e li normalizza a [-1, +1].
Output = position target per ogni candela.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

DEFAULT_LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250)


def donchian_signal(
    df: pd.DataFrame,
    lookbacks: tuple[int, ...] = DEFAULT_LOOKBACKS,
) -> pd.Series:
    """Calcola signal ensemble in [-1, +1].

    df deve avere colonne 'high', 'low', 'close' indexed by timestamp.
    """
    signals = []
    for L in lookbacks:
        upper = df["high"].rolling(window=L, min_periods=L).max()
        lower = df["low"].rolling(window=L, min_periods=L).min()
        sig = pd.Series(0.0, index=df.index, dtype=float)
        sig = sig.mask(df["close"] >= upper.shift(1), 1.0)
        sig = sig.mask(df["close"] <= lower.shift(1), -1.0)
        # Carry-forward last non-zero signal until opposite triggers
        sig = sig.replace(0.0, np.nan).ffill().fillna(0.0)
        signals.append(sig)
    ensemble = pd.concat(signals, axis=1).mean(axis=1)
    return ensemble.clip(-1.0, 1.0)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range — volatility proxy per position sizing + trailing stop."""
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, adjust=False, min_periods=period).mean()


def volatility_target_weight(
    df: pd.DataFrame,
    *,
    target_vol_annual: float = 0.40,
    vol_lookback: int = 30,
    bar_periods_per_year: int = 365,
) -> pd.Series:
    """Sizing inverso volatility realizzata.

    target_vol_annual default 40% per coin (high-vol asset class).
    Weight = target_vol / realized_vol, capped to [0, 1].
    """
    rets = df["close"].pct_change()
    realized = rets.rolling(window=vol_lookback, min_periods=vol_lookback).std() * np.sqrt(
        bar_periods_per_year
    )
    weight = (target_vol_annual / realized).clip(lower=0.0, upper=1.0)
    return weight.fillna(0.0)
