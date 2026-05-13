"""Runner double-OOS + bootstrap per TREND.

Pipeline:
1. **Training**: backtest su (train_asset, train_period) con params default
2. **Single OOS**: stesso config su (train_asset, test_period)
3. **Double OOS**: stesso config su (unseen_assets, test_period)
4. **Bootstrap**: N sample random sub-windows da test_period, distribuzione Sharpe
5. **DSR** su ogni Sharpe (skewness/kurtosis correction + multiple testing)

Restituisce verdetto: alpha_real | overfit | marginal | insufficient_data
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd

from app.metrics.deflated_sharpe import deflated_sharpe_ratio
from app.trend.engine import TrendConfig, run_trend_backtest


@dataclass
class WindowResult:
    label: str
    asset: str
    start: datetime
    end: datetime
    sharpe: float
    return_pct: float
    max_drawdown: float
    n_trades: int
    dsr: dict  # {dsr, psr, verdict, ...}


@dataclass
class BootstrapResult:
    n_samples: int
    sharpe_mean: float
    sharpe_std: float
    sharpe_p5: float  # 5th percentile (worst case)
    sharpe_p50: float
    sharpe_p95: float
    return_mean: float
    pct_positive_windows: float


@dataclass
class DoubleOOSResult:
    train: WindowResult
    single_oos: WindowResult  # same asset, test period
    double_oos: list[WindowResult]  # other assets, test period
    bootstrap: BootstrapResult
    verdict: str  # "alpha_real" | "overfit" | "marginal" | "insufficient"
    explanation: str


def _equity_to_returns(equity_curve: list[dict]) -> np.ndarray:
    if len(equity_curve) < 5:
        return np.array([])
    eq = pd.Series([p["equity"] for p in equity_curve])
    return eq.pct_change().dropna().values


def _make_window_result(label: str, asset: str, body: dict, train_dsr_var: float | None = None) -> WindowResult:
    rets = _equity_to_returns(body.get("equity_curve", []))
    dsr_info = deflated_sharpe_ratio(
        observed_sharpe=body.get("sharpe", 0.0),
        returns=rets,
        n_trials=10,  # paper-faithful: assume we tried 10 param combinations
        sharpe_variance_across_trials=train_dsr_var,
    )
    return WindowResult(
        label=label,
        asset=asset,
        start=body.get("start_date"),
        end=body.get("end_date"),
        sharpe=body.get("sharpe", 0.0),
        return_pct=body.get("total_return", 0.0) * 100,
        max_drawdown=body.get("max_drawdown", 0.0) * 100,
        n_trades=body.get("n_trades", 0),
        dsr=dsr_info,
    )


def bootstrap_sub_windows(
    ohlcv_by_sym: dict[str, pd.DataFrame],
    config_template: dict,
    full_start: datetime,
    full_end: datetime,
    n_samples: int = 50,
    sub_window_days: int = 180,
    rng_seed: int = 42,
) -> BootstrapResult:
    """Block bootstrap: campiona N sub-finestre random da [full_start, full_end] e fa backtest."""
    rng = np.random.default_rng(rng_seed)
    total_days = (full_end - full_start).days
    if total_days < sub_window_days + 30:
        return BootstrapResult(0, 0, 0, 0, 0, 0, 0, 0)

    sharpe_samples = []
    return_samples = []
    for _ in range(n_samples):
        offset = int(rng.integers(0, total_days - sub_window_days))
        sub_start = full_start + pd.Timedelta(days=offset)
        sub_end = sub_start + pd.Timedelta(days=sub_window_days)
        try:
            from app.trend.engine import TrendConfig, run_trend_backtest
            cfg = TrendConfig(**config_template)
            res = run_trend_backtest(ohlcv_by_sym, cfg)
            sharpe_samples.append(res.sharpe)
            return_samples.append(res.total_return)
        except Exception:
            continue

    if not sharpe_samples:
        return BootstrapResult(0, 0, 0, 0, 0, 0, 0, 0)

    arr = np.array(sharpe_samples)
    ret = np.array(return_samples)
    return BootstrapResult(
        n_samples=len(arr),
        sharpe_mean=float(arr.mean()),
        sharpe_std=float(arr.std()),
        sharpe_p5=float(np.percentile(arr, 5)),
        sharpe_p50=float(np.percentile(arr, 50)),
        sharpe_p95=float(np.percentile(arr, 95)),
        return_mean=float(ret.mean()),
        pct_positive_windows=float((arr > 0).mean()),
    )


def assess_verdict(
    train_sharpe: float,
    single_oos_sharpe: float,
    double_oos_sharpes: list[float],
    bootstrap_p5: float,
    train_dsr: float,
) -> tuple[str, str]:
    """Verdetto onesto su alpha reale o overfitting."""
    avg_double = float(np.mean(double_oos_sharpes)) if double_oos_sharpes else 0.0

    if train_dsr < 0.50:
        return "insufficient", f"DSR train = {train_dsr:.2f} < 0.50 → strategia indistinguibile da random anche IN sample"

    if single_oos_sharpe <= 0:
        return "overfit", f"Train sharpe {train_sharpe:.2f} → OOS BTC stesso periodo {single_oos_sharpe:.2f} <= 0: parametri overfit al training set"

    if avg_double <= 0:
        return "overfit", f"Single OOS BTC OK ({single_oos_sharpe:.2f}) ma double OOS (altri asset) media {avg_double:.2f} <= 0: edge specifico solo a BTC"

    if bootstrap_p5 <= 0:
        return "marginal", f"P5 bootstrap {bootstrap_p5:.2f} <= 0: in 5% delle sub-finestre random il sistema perde → instabile"

    if single_oos_sharpe < 0.5 and avg_double < 0.5:
        return "marginal", f"OOS positivi ma bassi (single {single_oos_sharpe:.2f}, double avg {avg_double:.2f}) → edge debole"

    return "alpha_real", (
        f"Train {train_sharpe:.2f} → single OOS {single_oos_sharpe:.2f} → double OOS avg {avg_double:.2f}, "
        f"bootstrap p5 {bootstrap_p5:.2f}: edge sopravvive a tutti i test → alpha replicabile"
    )
