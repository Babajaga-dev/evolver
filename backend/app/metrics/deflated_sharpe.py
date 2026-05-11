"""Deflated Sharpe Ratio (DSR) — Bailey & López de Prado SSRN 2460551.

Corregge per (a) multiple testing (quante strategie hai testato per trovare
quella "buona") e (b) non-normalità dei returns (skew/kurtosis).

Ritorna PROBABILITÀ in [0,1] che lo Sharpe osservato sia veramente > 0:
- < 0.50: probabile falso positivo
- 0.80-0.95: significativo
- > 0.95: altamente significativo

Reference: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
"""

from __future__ import annotations
import math
from typing import Sequence
import numpy as np
from scipy import stats

EULER_GAMMA = 0.5772156649015328606


def expected_max_sharpe(sharpe_variance_across_trials: float, n_trials: int) -> float:
    """E[max SR] su N trial random sotto null H_0=0.

    Formula chiusa: sqrt(V) * ((1-γ)·Φ^-1(1-1/N) + γ·Φ^-1(1-1/(N·e)))
    """
    if n_trials < 2:
        return 0.0
    std_sr = math.sqrt(max(sharpe_variance_across_trials, 1e-12))
    q1 = stats.norm.ppf(1.0 - 1.0 / n_trials)
    q2 = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return std_sr * ((1.0 - EULER_GAMMA) * q1 + EULER_GAMMA * q2)


def probabilistic_sharpe_ratio(
    observed_sharpe: float,
    returns: Sequence[float] | np.ndarray,
    sr_benchmark: float = 0.0,
) -> float:
    """PSR (no multiple testing correction)."""
    arr = np.asarray(returns, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 5:
        return 0.5
    g3 = float(stats.skew(arr, bias=False))
    g4 = float(stats.kurtosis(arr, bias=False, fisher=True)) + 3.0
    sr = float(observed_sharpe)
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return 0.5
    z = (sr - sr_benchmark) * math.sqrt(max(n - 1, 1)) / math.sqrt(denom)
    return float(stats.norm.cdf(z))


def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    returns: Sequence[float] | np.ndarray,
    n_trials: int,
    sharpe_variance_across_trials: float | None = None,
) -> dict:
    """DSR completo: PSR + multiple testing correction.

    Returns dict {dsr, psr, sr_threshold, n_trials, skewness, kurtosis, verdict}
    """
    arr = np.asarray(returns, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = len(arr)
    if n < 5:
        return {"dsr": 0.5, "psr": 0.5, "sr_threshold": 0.0, "n_trials": n_trials,
                "skewness": 0.0, "kurtosis": 3.0, "verdict": "insufficient_data"}
    g3 = float(stats.skew(arr, bias=False))
    g4 = float(stats.kurtosis(arr, bias=False, fisher=True)) + 3.0
    sr = float(observed_sharpe)
    if sharpe_variance_across_trials is None:
        sharpe_variance_across_trials = 0.5
    sr_0 = expected_max_sharpe(sharpe_variance_across_trials, n_trials)
    denom = 1.0 - g3 * sr + (g4 - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        dsr_val = 0.5
    else:
        z = (sr - sr_0) * math.sqrt(max(n - 1, 1)) / math.sqrt(denom)
        dsr_val = float(stats.norm.cdf(z))
    psr_val = probabilistic_sharpe_ratio(sr, arr, sr_benchmark=0.0)
    if dsr_val < 0.50:
        verdict = "false_positive"
    elif dsr_val < 0.80:
        verdict = "marginal"
    elif dsr_val < 0.95:
        verdict = "significant"
    else:
        verdict = "highly_significant"
    return {"dsr": dsr_val, "psr": psr_val, "sr_threshold": float(sr_0),
            "n_trials": int(n_trials), "skewness": g3, "kurtosis": g4, "verdict": verdict}
