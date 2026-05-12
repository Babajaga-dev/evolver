"""Engine StatArb pairs trade cointegration.

Algoritmo:
- Rolling cointegration test: regressione OLS log(P_A) ~ beta*log(P_B), residui = spread
- Z-score = (spread - mean) / std rolling
- Trade rules: entry |Z|>2, exit |Z|<0.5, stop |Z|>3.5
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller


@dataclass
class StatArbConfig:
    symbol_a: str = "BTC/USDT"
    symbol_b: str = "ETH/USDT"
    timeframe: str = "4h"
    lookback_bars: int = 180  # rolling window for hedge ratio + z-score
    z_entry: float = 2.0
    z_exit: float = 0.5
    z_stop: float = 3.5
    max_half_life_bars: int = 180  # skip if MR too slow
    initial_cash: float = 10_000.0
    capital_per_trade: float = 0.50  # use 50% of equity per leg
    fee_bps: float = 4.0  # per-leg taker
    slippage_bps: float = 2.0


@dataclass
class StatArbTrade:
    entry_time: datetime
    exit_time: datetime
    side: str  # "long_spread" (long A, short B) or "short_spread"
    entry_spread: float
    exit_spread: float
    entry_z: float
    exit_z: float
    qty_a: float
    qty_b: float
    pnl: float
    pnl_pct: float
    holding_bars: int
    reason: str  # "z_exit" / "z_stop" / "end"


@dataclass
class StatArbEquityPoint:
    t: datetime
    equity: float
    spread: float
    zscore: float
    hedge_ratio: float
    position: int  # -1, 0, +1


@dataclass
class StatArbResult:
    config: StatArbConfig
    start_date: datetime
    end_date: datetime
    n_trades: int
    n_winners: int
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    avg_holding_bars: float
    beta_vs_btc: float  # market neutral check
    avg_hedge_ratio: float
    cointegration_p_value: float  # last ADF test p-value
    equity_curve: list[StatArbEquityPoint]
    trades: list[StatArbTrade] = field(default_factory=list)
    monthly_returns: list[dict] = field(default_factory=list)


def _bppy(tf: str) -> int:
    return {"1h": 24 * 365, "4h": 6 * 365, "1d": 365}.get(tf, 365)


def _half_life(spread: pd.Series) -> float:
    """Half-life di mean reversion via OU process AR(1)."""
    diff = spread.diff().dropna()
    lagged = spread.shift(1).dropna()
    aligned = pd.concat([diff, lagged], axis=1).dropna()
    if len(aligned) < 30:
        return float("inf")
    x = aligned.iloc[:, 1].values
    y = aligned.iloc[:, 0].values
    # OLS: dy = -theta * x + epsilon → half-life = ln(2)/theta
    theta = -float(np.cov(x, y, ddof=0)[0, 1] / np.var(x))
    if theta <= 0:
        return float("inf")
    return float(np.log(2) / theta)


def run_statarb_backtest(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    config: StatArbConfig,
) -> StatArbResult:
    """Backtest pairs trade su (df_a, df_b) con cointegration rolling.

    Assume timeframes allineati e indici time-sorted.
    """
    # Align
    df = pd.DataFrame({
        "close_a": df_a["close"].astype(float),
        "close_b": df_b["close"].astype(float),
    }).dropna()
    if len(df) < config.lookback_bars + 50:
        raise ValueError(f"Dati insufficienti: serve >= {config.lookback_bars+50} bars, got {len(df)}")

    log_a = np.log(df["close_a"])
    log_b = np.log(df["close_b"])

    # Rolling regression: log_a = alpha + beta * log_b → residual = log_a - alpha - beta*log_b
    L = config.lookback_bars
    hedge_ratios = pd.Series(np.nan, index=df.index)
    alphas = pd.Series(np.nan, index=df.index)
    spreads = pd.Series(np.nan, index=df.index)
    z_scores = pd.Series(np.nan, index=df.index)

    for i in range(L, len(df)):
        wa = log_a.iloc[i - L:i].values
        wb = log_b.iloc[i - L:i].values
        # OLS via numpy
        beta, alpha = np.polyfit(wb, wa, 1)
        hedge_ratios.iloc[i] = beta
        alphas.iloc[i] = alpha
        residual_window = wa - (alpha + beta * wb)
        spread_now = float(log_a.iloc[i] - (alpha + beta * log_b.iloc[i]))
        spreads.iloc[i] = spread_now
        mu = float(np.mean(residual_window))
        sigma = float(np.std(residual_window, ddof=1))
        if sigma > 0:
            z_scores.iloc[i] = (spread_now - mu) / sigma

    # Last cointegration ADF test on full residual series for diagnostic
    valid_spread = spreads.dropna()
    if len(valid_spread) > 30:
        try:
            adf_stat, p_value, *_ = adfuller(valid_spread.values, autolag="AIC")
        except Exception:
            p_value = 1.0
    else:
        p_value = 1.0

    bppy = _bppy(config.timeframe)
    cost = (config.fee_bps + config.slippage_bps) / 10_000.0

    # Simulate trades
    equity = config.initial_cash
    cash = config.initial_cash
    position_state = 0  # -1 short spread (short A long B), 0 flat, +1 long spread (long A short B)
    qty_a = 0.0
    qty_b = 0.0
    entry_price_a = 0.0
    entry_price_b = 0.0
    entry_t = None
    entry_z_val = 0.0
    entry_spread_val = 0.0

    trades: list[StatArbTrade] = []
    eq_curve: list[StatArbEquityPoint] = []

    for ts, row in df.iterrows():
        z = z_scores.get(ts, np.nan)
        spread_now = spreads.get(ts, np.nan)
        beta = hedge_ratios.get(ts, np.nan)
        pa = float(row["close_a"])
        pb = float(row["close_b"])

        # Mark-to-market
        if position_state != 0:
            # long spread: long A, short B (hedge ratio beta)
            # PnL = qty_a*(pa-entry_a) - qty_b*(pb-entry_b)
            mtm_a = qty_a * (pa - entry_price_a)
            mtm_b = qty_b * (pb - entry_price_b)
            if position_state == 1:
                pnl_open = mtm_a - mtm_b
            else:
                pnl_open = -mtm_a + mtm_b
            equity = cash + pnl_open
        else:
            equity = cash

        # Exit logic
        exit_reason = None
        if position_state != 0 and not np.isnan(z):
            if abs(z) <= config.z_exit:
                exit_reason = "z_exit"
            elif abs(z) >= config.z_stop:
                exit_reason = "z_stop"

        if exit_reason:
            if position_state == 1:
                exit_pnl = qty_a * (pa - entry_price_a) - qty_b * (pb - entry_price_b)
            else:
                exit_pnl = -qty_a * (pa - entry_price_a) + qty_b * (pb - entry_price_b)
            exit_cost = (qty_a * pa + qty_b * pb) * cost
            net_pnl = exit_pnl - exit_cost
            cash = cash + net_pnl
            pnl_pct = net_pnl / config.initial_cash
            trades.append(
                StatArbTrade(
                    entry_time=entry_t,
                    exit_time=ts,
                    side="long_spread" if position_state == 1 else "short_spread",
                    entry_spread=entry_spread_val,
                    exit_spread=float(spread_now) if not np.isnan(spread_now) else 0.0,
                    entry_z=entry_z_val,
                    exit_z=float(z) if not np.isnan(z) else 0.0,
                    qty_a=qty_a,
                    qty_b=qty_b,
                    pnl=net_pnl,
                    pnl_pct=pnl_pct,
                    holding_bars=int((ts - entry_t).total_seconds() / 3600 / (4 if config.timeframe == "4h" else (1 if config.timeframe == "1h" else 24))) if entry_t else 0,
                    reason=exit_reason,
                )
            )
            position_state = 0
            qty_a = qty_b = 0.0

        # Entry logic
        if position_state == 0 and not np.isnan(z) and not np.isnan(beta) and beta > 0:
            if abs(z) >= config.z_entry:
                # Half-life filter
                start_pos = max(0, df.index.get_loc(ts) - L)
                spread_window = spreads.iloc[start_pos:df.index.get_loc(ts)+1].dropna()
                hl = _half_life(spread_window) if len(spread_window) > 30 else float("inf")
                if hl > config.max_half_life_bars or hl <= 0:
                    eq_curve.append(
                        StatArbEquityPoint(
                            t=ts, equity=float(equity), spread=float(spread_now) if not np.isnan(spread_now) else 0.0,
                            zscore=float(z), hedge_ratio=float(beta), position=position_state,
                        )
                    )
                    continue
                # Open trade
                capital = equity * config.capital_per_trade
                # qty_a in coin A, qty_b = beta * qty_a (notional hedge)
                qty_a_notional = capital / 2
                qty_b_notional = capital / 2
                qty_a = qty_a_notional / pa
                qty_b = qty_b_notional / pb
                entry_price_a = pa
                entry_price_b = pb
                entry_t = ts
                entry_z_val = float(z)
                entry_spread_val = float(spread_now)
                if z > 0:
                    # spread above mean → short spread (short A, long B)
                    position_state = -1
                else:
                    position_state = 1
                entry_cost = (qty_a * pa + qty_b * pb) * cost
                cash -= entry_cost
                equity = cash

        eq_curve.append(
            StatArbEquityPoint(
                t=ts,
                equity=float(equity),
                spread=float(spread_now) if not np.isnan(spread_now) else 0.0,
                zscore=float(z) if not np.isnan(z) else 0.0,
                hedge_ratio=float(beta) if not np.isnan(beta) else 0.0,
                position=position_state,
            )
        )

    # Close any open position
    if position_state != 0 and eq_curve:
        ts = eq_curve[-1].t
        pa = float(df.loc[ts, "close_a"])
        pb = float(df.loc[ts, "close_b"])
        if position_state == 1:
            net = qty_a * (pa - entry_price_a) - qty_b * (pb - entry_price_b)
        else:
            net = -qty_a * (pa - entry_price_a) + qty_b * (pb - entry_price_b)
        exit_cost = (qty_a * pa + qty_b * pb) * cost
        net -= exit_cost
        cash += net
        equity = cash
        trades.append(StatArbTrade(
            entry_time=entry_t, exit_time=ts,
            side="long_spread" if position_state == 1 else "short_spread",
            entry_spread=entry_spread_val,
            exit_spread=float(spreads.get(ts, 0.0) or 0.0),
            entry_z=entry_z_val,
            exit_z=float(z_scores.get(ts, 0.0) or 0.0),
            qty_a=qty_a, qty_b=qty_b, pnl=net, pnl_pct=net/config.initial_cash,
            holding_bars=0, reason="end",
        ))

    # Metrics
    eq_series = pd.Series([p.equity for p in eq_curve], index=[p.t for p in eq_curve])
    rets = eq_series.pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(bppy)) if rets.std() > 0 else 0.0
    down = rets[rets < 0]
    sortino = float(rets.mean() / down.std() * np.sqrt(bppy)) if len(down) > 0 and down.std() > 0 else 0.0
    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = float(dd.min()) if len(dd) else 0.0
    n_winners = sum(1 for t in trades if t.pnl > 0)
    win_rate = n_winners / max(len(trades), 1)
    avg_hold = float(np.mean([t.holding_bars for t in trades])) if trades else 0.0
    final_equity = float(eq_series.iloc[-1]) if len(eq_series) else config.initial_cash
    total_return = (final_equity - config.initial_cash) / config.initial_cash

    # Beta vs BTC for market-neutral check
    btc_rets = df["close_a"].pct_change().dropna()
    aligned = pd.concat([rets, btc_rets], axis=1).dropna()
    aligned.columns = ["strategy", "btc"]
    if len(aligned) > 20 and aligned["btc"].std() > 0:
        beta_vs_btc = float(np.cov(aligned["strategy"], aligned["btc"], ddof=0)[0, 1] / np.var(aligned["btc"]))
    else:
        beta_vs_btc = 0.0

    avg_hr = float(np.nanmean(hedge_ratios.values))

    monthly = []
    if len(eq_series):
        eq_m = eq_series.resample("ME").last().pct_change().dropna()
        for ts, ret in eq_m.items():
            n_t = sum(1 for t in trades if t.exit_time.year == ts.year and t.exit_time.month == ts.month)
            monthly.append({"month": ts.strftime("%Y-%m"), "return_pct": float(ret * 100), "n_trades": n_t})

    return StatArbResult(
        config=config,
        start_date=df.index[0],
        end_date=df.index[-1],
        n_trades=len(trades),
        n_winners=n_winners,
        initial_cash=config.initial_cash,
        final_equity=final_equity,
        total_return=total_return,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        win_rate=win_rate,
        avg_holding_bars=avg_hold,
        beta_vs_btc=beta_vs_btc,
        avg_hedge_ratio=avg_hr,
        cointegration_p_value=float(p_value),
        equity_curve=eq_curve,
        trades=trades,
        monthly_returns=monthly,
    )
