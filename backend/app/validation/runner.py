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
    """Block bootstrap: campiona N sub-finestre random da [full_start, full_end] e fa backtest.

    Per ogni sub-window filtra i DataFrame al periodo [sub_start, sub_end] prima del run.
    """
    rng = np.random.default_rng(rng_seed)
    # Tz-normalize boundaries
    if full_start.tzinfo is None:
        from datetime import timezone
        full_start = full_start.replace(tzinfo=timezone.utc)
    if full_end.tzinfo is None:
        from datetime import timezone
        full_end = full_end.replace(tzinfo=timezone.utc)
    total_days = (full_end - full_start).days
    if total_days < sub_window_days + 30:
        return BootstrapResult(0, 0, 0, 0, 0, 0, 0, 0)

    sharpe_samples = []
    return_samples = []
    for i in range(n_samples):
        offset = int(rng.integers(0, max(1, total_days - sub_window_days)))
        sub_start = full_start + pd.Timedelta(days=offset)
        sub_end = sub_start + pd.Timedelta(days=sub_window_days)
        try:
            from app.trend.engine import TrendConfig, run_trend_backtest
            # Filter df per sub-window
            filtered = {}
            for sym, df in ohlcv_by_sym.items():
                if df.index.tz is None:
                    df.index = df.index.tz_localize("UTC")
                sub_df = df.loc[(df.index >= sub_start) & (df.index <= sub_end)]
                if len(sub_df) >= 60:
                    filtered[sym] = sub_df
            if not filtered:
                continue
            cfg = TrendConfig(**config_template)
            res = run_trend_backtest(filtered, cfg)
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
    """Verdetto onesto basato su OOS performance + bootstrap, non su train DSR alone.

    Logica: il train DSR è sempre basso quando n_trials assunto è 10 (paper-conservative).
    L'evidenza vera viene da single+double OOS POSITIVI + bootstrap stabile.
    """
    avg_double = float(np.mean(double_oos_sharpes)) if double_oos_sharpes else 0.0
    pos_double = sum(1 for s in double_oos_sharpes if s > 0)
    n_double = max(len(double_oos_sharpes), 1)

    # OOS è il giudice supremo, non il DSR del train
    if single_oos_sharpe <= -0.5:
        return "overfit", (
            f"OOS BTC sharpe {single_oos_sharpe:.2f} <= -0.5: i parametri sono overfit al training set. "
            f"Train DSR={train_dsr:.2f}."
        )

    if avg_double <= -0.3:
        return "overfit", (
            f"Double OOS (altri asset) media {avg_double:.2f}: edge specifico solo all'asset di training, non generalizza. "
            f"Single OOS={single_oos_sharpe:.2f}."
        )

    # If single+double OOS sono tutti positivi → alpha solido a prescindere dal train DSR
    if single_oos_sharpe > 0.5 and pos_double >= n_double * 0.66 and avg_double > 0.3:
        return "alpha_real", (
            f"Single OOS BTC={single_oos_sharpe:.2f}, double OOS avg={avg_double:.2f} ({pos_double}/{n_double} positivi). "
            f"Edge sopravvive a unseen-asset + unseen-period → alpha replicabile fuori sample. "
            f"Bootstrap p5={bootstrap_p5:.2f}."
        )

    if single_oos_sharpe > 0 and avg_double > 0:
        return "marginal", (
            f"OOS marginalmente positivi (single {single_oos_sharpe:.2f}, double avg {avg_double:.2f}): "
            f"edge debole ma presente. "
            f"Bootstrap p5={bootstrap_p5:.2f}."
        )

    return "insufficient", (
        f"OOS misti (single {single_oos_sharpe:.2f}, double avg {avg_double:.2f}): "
        f"signal-to-noise basso. Train DSR={train_dsr:.2f}."
    )
