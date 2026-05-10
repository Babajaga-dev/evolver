"""Council strategy — 4 indicatori × 3 timeframe + regime-aware combination.

Vocabolario:
    Voter = (indicator, timeframe) → segnale -1 / 0 / +1 (short/flat/long)
    Council = aggregazione di N voter con peso regime-dependent
    Organism = Council + parametri evoluti per quel momento

Indicatori usati:
    rsi (mean-reversion): -1 se RSI>sell_above, +1 se RSI<buy_below
    macd (trend follow): segno di (macd - signal)
    bb_breakout (volatility): +1 se close>upper, -1 se close<lower
    ema_cross (trend conf): +1 se ema_fast>ema_slow, -1 altrimenti

Decisione finale:
    score = Σ w_i * vote_i  (w_i dipende dal regime corrente)
    position = clip(score, -1, +1) * position_size_pct

Per semplicità slice iniziale: solo posizioni LONG (long-only).
score > 0.5 → long full, score 0.2-0.5 → long half, score < 0.2 → flat
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.indicators.core import compute as compute_indicator


INDICATORS = ("rsi", "macd", "bb_breakout", "ema_cross")
TIMEFRAMES = ("1h", "4h", "1d")
REGIMES = ("trend_bullish", "trend_bearish", "trend_mixed", "range_low_vol",
           "range_high_vol", "range", "transition")


@dataclass
class VoterParams:
    """Parametri per un singolo (indicator, tf) voter."""
    rsi_period: int = 14
    rsi_buy_below: float = 30.0
    rsi_sell_above: float = 70.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    ema_fast: int = 12
    ema_slow: int = 26


def _vote_rsi(df: pd.DataFrame, p: VoterParams) -> pd.Series:
    out, _ = compute_indicator("rsi", df, {"period": p.rsi_period})
    rsi = out["rsi"]
    s = pd.Series(0.0, index=df.index)
    s[rsi < p.rsi_buy_below] = 1.0
    s[rsi > p.rsi_sell_above] = -1.0
    return s.fillna(0.0)


def _vote_macd(df: pd.DataFrame, p: VoterParams) -> pd.Series:
    if p.macd_fast >= p.macd_slow:
        return pd.Series(0.0, index=df.index)
    out, _ = compute_indicator("macd", df, {
        "fast": p.macd_fast, "slow": p.macd_slow, "signal": p.macd_signal
    })
    diff = out["macd"] - out["signal"]
    s = pd.Series(0.0, index=df.index)
    s[diff > 0] = 1.0
    s[diff < 0] = -1.0
    return s.fillna(0.0)


def _vote_bb(df: pd.DataFrame, p: VoterParams) -> pd.Series:
    out, _ = compute_indicator("bbands", df, {"period": p.bb_period, "std": p.bb_std})
    upper = out["upper"]; lower = out["lower"]; close = df["close"]
    s = pd.Series(0.0, index=df.index)
    s[close > upper] = 1.0
    s[close < lower] = -1.0
    return s.fillna(0.0)


def _vote_ema(df: pd.DataFrame, p: VoterParams) -> pd.Series:
    if p.ema_fast >= p.ema_slow:
        return pd.Series(0.0, index=df.index)
    fast, _ = compute_indicator("ema", df, {"period": p.ema_fast})
    slow, _ = compute_indicator("ema", df, {"period": p.ema_slow})
    diff = fast["ema"] - slow["ema"]
    s = pd.Series(0.0, index=df.index)
    s[diff > 0] = 1.0
    s[diff < 0] = -1.0
    return s.fillna(0.0)


VOTER_FNS = {
    "rsi": _vote_rsi,
    "macd": _vote_macd,
    "bb_breakout": _vote_bb,
    "ema_cross": _vote_ema,
}


@dataclass
class CouncilParams:
    """Parametri completi di un Council = 12 voter + pesi per regime.

    Genoma totale:
        12 voter × ~3 params = ~24 numeri (alcuni condivisi)
        + matrice pesi per regime: 7 regimi × 4 indicatori = 28 pesi
        TOTALE: ~50 dim (più la position_size_pct universale)
    """
    voters: dict[str, VoterParams] = field(default_factory=dict)
    # key: "{indicator}_{tf}" → params (es. "rsi_4h" → VoterParams)
    weights: dict[str, dict[str, float]] = field(default_factory=dict)
    # weights[regime][indicator] = peso (0-1)
    position_size_pct: float = 50.0

    def get_voter(self, indicator: str, tf: str) -> VoterParams:
        return self.voters.get(f"{indicator}_{tf}", VoterParams())

    def get_weight(self, regime: str, indicator: str) -> float:
        return self.weights.get(regime, {}).get(indicator, 0.25)


def default_council_params() -> CouncilParams:
    """Council baseline con params textbook + pesi neutri per ogni regime."""
    voters = {}
    for ind in INDICATORS:
        for tf in TIMEFRAMES:
            voters[f"{ind}_{tf}"] = VoterParams()
    # Pesi default: in trend, MACD+EMA pesano 70%; in range, RSI+BB pesano 70%
    weights = {
        "trend_bullish":   {"rsi": 0.10, "macd": 0.40, "bb_breakout": 0.10, "ema_cross": 0.40},
        "trend_bearish":   {"rsi": 0.10, "macd": 0.40, "bb_breakout": 0.10, "ema_cross": 0.40},
        "trend_mixed":     {"rsi": 0.25, "macd": 0.25, "bb_breakout": 0.25, "ema_cross": 0.25},
        "range_low_vol":   {"rsi": 0.40, "macd": 0.10, "bb_breakout": 0.40, "ema_cross": 0.10},
        "range_high_vol":  {"rsi": 0.30, "macd": 0.10, "bb_breakout": 0.50, "ema_cross": 0.10},
        "range":           {"rsi": 0.35, "macd": 0.10, "bb_breakout": 0.45, "ema_cross": 0.10},
        "transition":      {"rsi": 0.0,  "macd": 0.0,  "bb_breakout": 0.0,  "ema_cross": 0.0},  # cash
    }
    return CouncilParams(voters=voters, weights=weights, position_size_pct=50.0)


def compute_signals_hierarchical(
    candles_by_tf: dict[str, pd.DataFrame],
    council: CouncilParams,
    regime_by_t: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Calcola entries/exits dal Council su candele 4h (TF primario).

    Args:
        candles_by_tf: {"1h": df_1h, "4h": df_4h, "1d": df_1d}
        council: parametri correnti
        regime_by_t: regime label per ogni timestamp di df_4h

    Returns:
        (entries, exits, position_size) su indice di df_4h
    """
    df_primary = candles_by_tf["4h"]
    n = len(df_primary)
    if n < 30:
        z = pd.Series(False, index=df_primary.index)
        return z, z, pd.Series(0.0, index=df_primary.index)

    # Per ogni voter, computa vote su SUO timeframe poi forward-fill su 4h
    votes_aligned: dict[str, dict[str, pd.Series]] = {ind: {} for ind in INDICATORS}
    for ind in INDICATORS:
        for tf in TIMEFRAMES:
            df_tf = candles_by_tf.get(tf)
            if df_tf is None or len(df_tf) < 30:
                continue
            params = council.get_voter(ind, tf)
            vote_tf = VOTER_FNS[ind](df_tf, params)
            # Reindex su df_primary index con forward fill
            vote_aligned = vote_tf.reindex(df_primary.index, method="ffill").fillna(0.0)
            votes_aligned[ind][tf] = vote_aligned

    # Aggrega per indicatore (media sui timeframe disponibili)
    indicator_score: dict[str, pd.Series] = {}
    for ind in INDICATORS:
        if votes_aligned[ind]:
            stacked = pd.concat(votes_aligned[ind].values(), axis=1)
            indicator_score[ind] = stacked.mean(axis=1)
        else:
            indicator_score[ind] = pd.Series(0.0, index=df_primary.index)

    # Score finale: somma pesata per regime
    regime_aligned = regime_by_t.reindex(df_primary.index, method="ffill").fillna("range")
    final_score = pd.Series(0.0, index=df_primary.index)
    for ind in INDICATORS:
        for regime in REGIMES:
            mask = regime_aligned == regime
            if not mask.any():
                continue
            weight = council.get_weight(regime, ind)
            final_score.loc[mask] += indicator_score[ind].loc[mask] * weight

    # Decisione long-only:
    entries = final_score > 0.3
    exits = final_score < 0.0
    # Position size scaling
    pos = (final_score.clip(0, 1.0) * council.position_size_pct).fillna(0.0)
    return entries.fillna(False), exits.fillna(False), pos
