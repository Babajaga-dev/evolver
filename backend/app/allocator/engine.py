"""Engine Risk Allocator — combina equity curves di 3 motori indipendenti.

Approccio Topological Risk Parity (arXiv 2604.16773): weight ~ 1/variance
con normalizzazione che mantiene sum=1. Aggiunge overlay GATE + F&G.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass
class AllocatorEngineRun:
    name: str
    equity_curve: list[dict]  # [{t, equity}]


@dataclass
class AllocatorConfig:
    rolling_sharpe_days: int = 30
    rebalance_days: int = 7
    initial_cash: float = 30_000.0  # split su 3 motori
    fng_extreme_fear_threshold: float = 25.0  # EMA-24w
    fng_extreme_greed_threshold: float = 75.0
    fng_extreme_boost: float = 1.30  # boost market-neutral in extreme zones
    fng_extreme_dampen: float = 0.50  # dampen trend in extreme greed (mean reversion)
    min_weight: float = 0.05  # avoid total exclusion (diversification floor)


@dataclass
class AllocatorPoint:
    t: datetime
    equity: float
    weight_trend: float
    weight_statarb: float
    weight_carry: float
    fng_ema: float | None
    regime: str  # bull / bear / neutral
    gate_active: bool


@dataclass
class AllocatorResult:
    config: AllocatorConfig
    start_date: datetime
    end_date: datetime
    n_rebalances: int
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    correlation_matrix: dict
    per_engine_contribution: dict  # {engine_name: total_pnl_contribution}
    equity_curve: list[AllocatorPoint]


def _bppy(tf: str = "1d") -> int:
    return 365


def run_allocator(
    engines: dict[str, pd.DataFrame],  # {name: DataFrame[index=t, col=equity]}
    fng_series: pd.Series | None,  # daily F&G value indexed by date
    regime_series: pd.Series | None,  # daily regime string indexed by date
    config: AllocatorConfig,
) -> AllocatorResult:
    """Aggrega equity curves di N motori in un equity allocator con weights dinamici.

    engines: dict name → DataFrame with column 'equity' indexed by datetime
    fng_series: optional Fear&Greed EMA-24w value, daily
    regime_series: optional regime string (bull/bear/transition), daily
    """
    if not engines:
        raise ValueError("Nessun motore fornito")

    # 1. Compute daily returns per engine, align on common index
    rets_by_engine: dict[str, pd.Series] = {}
    for name, df in engines.items():
        if "equity" not in df.columns:
            continue
        eq = df["equity"].astype(float)
        # Resample to daily for alignment
        eq_d = eq.resample("D").last().ffill()
        rets = eq_d.pct_change().fillna(0.0)
        rets_by_engine[name] = rets

    if not rets_by_engine:
        raise ValueError("Nessun motore valido con equity")

    common_idx = sorted(set.intersection(*[set(r.index) for r in rets_by_engine.values()]))
    if not common_idx:
        raise ValueError("Nessuna data comune tra i motori")

    rets_df = pd.DataFrame({n: r.reindex(common_idx) for n, r in rets_by_engine.items()}).fillna(0.0)

    # 2. Simulate allocator
    equity = config.initial_cash
    cash_per_engine = {n: config.initial_cash / len(rets_df.columns) for n in rets_df.columns}
    weights = {n: 1.0 / len(rets_df.columns) for n in rets_df.columns}
    curve: list[AllocatorPoint] = []
    last_rebal = -config.rebalance_days

    # Engine PnL tracking
    engine_pnl_contribution: dict[str, float] = {n: 0.0 for n in rets_df.columns}

    for bar_i, t in enumerate(rets_df.index):
        # Periodic rebalance
        if bar_i - last_rebal >= config.rebalance_days:
            last_rebal = bar_i
            # Inverse-variance over rolling window
            start = max(0, bar_i - config.rolling_sharpe_days)
            window = rets_df.iloc[start:bar_i+1]
            if len(window) >= 5:
                variances = window.var()
                # Avoid divide-by-zero
                variances = variances.replace(0, variances.max() if variances.max() > 0 else 1e-6)
                inv_var = 1.0 / variances
                raw_weights = inv_var / inv_var.sum()
                weights = raw_weights.to_dict()

                # F&G overlay
                if fng_series is not None and t in fng_series.index:
                    fng_val = float(fng_series.loc[t])
                    if fng_val >= config.fng_extreme_greed_threshold:
                        # Extreme greed → dampen trend, boost market-neutral
                        if "trend" in weights:
                            weights["trend"] *= config.fng_extreme_dampen
                        for n in ("statarb", "carry"):
                            if n in weights:
                                weights[n] *= config.fng_extreme_boost
                    elif fng_val <= config.fng_extreme_fear_threshold:
                        # Extreme fear → dampen trend, slight boost market-neutral
                        if "trend" in weights:
                            weights["trend"] *= config.fng_extreme_dampen
                        for n in ("statarb", "carry"):
                            if n in weights:
                                weights[n] *= config.fng_extreme_boost

                # GATE regime overlay
                gate_active = False
                if regime_series is not None and t in regime_series.index:
                    reg = str(regime_series.loc[t])
                    if reg in ("trend_bearish", "transition", "bear"):
                        if "trend" in weights:
                            weights["trend"] = max(weights["trend"] * 0.2, config.min_weight)
                        gate_active = True

                # Renormalize
                total = sum(weights.values())
                if total > 0:
                    weights = {k: v / total for k, v in weights.items()}
                # Min weight floor
                weights = {k: max(v, config.min_weight) for k, v in weights.items()}
                total = sum(weights.values())
                weights = {k: v / total for k, v in weights.items()}

                # Rebalance cash splits to match weights
                cash_per_engine = {k: equity * v for k, v in weights.items()}

        # Apply daily returns per engine
        new_equity = 0.0
        for n in rets_df.columns:
            r = float(rets_df.loc[t, n])
            cash_per_engine[n] *= (1 + r)
            pnl_today = cash_per_engine[n] * r / (1 + r) if r != -1 else 0.0
            engine_pnl_contribution[n] += pnl_today
            new_equity += cash_per_engine[n]
        equity = new_equity

        fng_val = None
        if fng_series is not None and t in fng_series.index:
            fng_val = float(fng_series.loc[t])
        regime = "neutral"
        gate_active = False
        if regime_series is not None and t in regime_series.index:
            regime = str(regime_series.loc[t])
            if regime in ("trend_bearish", "transition", "bear"):
                gate_active = True

        curve.append(
            AllocatorPoint(
                t=t,
                equity=float(equity),
                weight_trend=float(weights.get("trend", 0.0)),
                weight_statarb=float(weights.get("statarb", 0.0)),
                weight_carry=float(weights.get("carry", 0.0)),
                fng_ema=fng_val,
                regime=regime,
                gate_active=gate_active,
            )
        )

    eq_series = pd.Series([p.equity for p in curve], index=[p.t for p in curve])
    daily_rets = eq_series.pct_change().dropna()
    sharpe = float(daily_rets.mean() / daily_rets.std() * np.sqrt(365)) if daily_rets.std() > 0 else 0.0
    down = daily_rets[daily_rets < 0]
    sortino = float(daily_rets.mean() / down.std() * np.sqrt(365)) if len(down) > 0 and down.std() > 0 else 0.0
    peak = eq_series.cummax()
    max_dd = float(((eq_series - peak) / peak).min()) if len(eq_series) > 0 else 0.0
    final = float(eq_series.iloc[-1]) if len(eq_series) else config.initial_cash
    total_ret = (final - config.initial_cash) / config.initial_cash

    corr = rets_df.corr()
    corr_dict = {
        col: {row: float(corr.loc[row, col]) for row in corr.columns}
        for col in corr.columns
    }

    return AllocatorResult(
        config=config,
        start_date=rets_df.index[0],
        end_date=rets_df.index[-1],
        n_rebalances=sum(1 for _ in range(0, len(rets_df), config.rebalance_days)),
        initial_cash=config.initial_cash,
        final_equity=final,
        total_return=total_ret,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        correlation_matrix=corr_dict,
        per_engine_contribution=engine_pnl_contribution,
        equity_curve=curve,
    )
