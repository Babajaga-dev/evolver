"""TREND backtest engine — Donchian ensemble + vol-targeting + trailing stop.

Approccio long-short asymmetric (paper AdaptiveTrend 70/30 default).
Output: equity curve + trades + monthly returns + per-asset breakdown.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd

from app.trend.donchian import (
    DEFAULT_LOOKBACKS,
    atr,
    donchian_signal,
    volatility_target_weight,
)


@dataclass
class TrendConfig:
    symbols: list[str]
    timeframe: str = "4h"
    lookbacks: tuple[int, ...] = DEFAULT_LOOKBACKS
    target_vol_annual: float = 0.40
    vol_lookback: int = 30
    atr_period: int = 14
    trailing_stop_atr_mult: float = 3.0
    rebalance_days: int = 30
    top_n_assets: int = 10
    long_weight: float = 0.70
    short_weight: float = 0.30
    fee_bps: float = 4.0  # taker fee 0.04%
    slippage_bps: float = 2.0
    initial_cash: float = 10_000.0
    sharpe_lookback_days: int = 90


@dataclass
class TrendTrade:
    symbol: str
    side: str  # "long" / "short"
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    pnl: float
    pnl_pct: float
    holding_days: float
    reason: str  # "signal" / "trailing_stop" / "rebalance"


@dataclass
class TrendResult:
    config: TrendConfig
    start_date: datetime
    end_date: datetime
    n_trades: int
    n_long_trades: int
    n_short_trades: int
    initial_cash: float
    final_equity: float
    total_return: float
    sharpe: float
    sortino: float
    max_drawdown: float
    win_rate: float
    avg_pnl_pct: float
    monthly_returns: list[dict]  # [{month, return_pct, n_trades}]
    equity_curve: list[dict]  # [{t, equity, exposure_pct, n_positions}]
    trades: list[TrendTrade] = field(default_factory=list)
    per_asset_stats: list[dict] = field(default_factory=list)


def _bar_periods_per_year(tf: str) -> int:
    return {
        "1h": 24 * 365,
        "4h": 6 * 365,
        "1d": 365,
    }.get(tf, 365)


def run_trend_backtest(
    ohlcv_by_symbol: dict[str, pd.DataFrame],
    config: TrendConfig,
) -> TrendResult:
    """Backtest portfolio Donchian ensemble.

    ohlcv_by_symbol: {symbol: DataFrame con cols [open,high,low,close,volume]
                      indexed by timestamp UTC}
    """
    if not ohlcv_by_symbol:
        raise ValueError("Nessun dato OHLCV fornito al motore TREND")

    bppy = _bar_periods_per_year(config.timeframe)

    # 1. Compute signals + vol weights per symbol
    signal_by_sym: dict[str, pd.Series] = {}
    vol_w_by_sym: dict[str, pd.Series] = {}
    atr_by_sym: dict[str, pd.Series] = {}
    for sym, df in ohlcv_by_symbol.items():
        if df.empty or len(df) < max(config.lookbacks):
            continue
        sig = donchian_signal(df, lookbacks=config.lookbacks)
        wv = volatility_target_weight(
            df,
            target_vol_annual=config.target_vol_annual,
            vol_lookback=config.vol_lookback,
            bar_periods_per_year=bppy,
        )
        signal_by_sym[sym] = sig
        vol_w_by_sym[sym] = wv
        atr_by_sym[sym] = atr(df, period=config.atr_period)

    if not signal_by_sym:
        raise ValueError("Nessun simbolo con dati sufficienti")

    # Align timestamp index
    all_idx = sorted(set().union(*[s.index for s in signal_by_sym.values()]))
    rebal_periods_per_day = bppy / 365
    bars_per_rebalance = int(config.rebalance_days * rebal_periods_per_day)

    # 2. Simulate
    cost_factor = (config.fee_bps + config.slippage_bps) / 10_000.0
    positions: dict[str, dict] = {}  # symbol -> {side, qty, entry_px, entry_t, trail_stop, hwm}
    equity = config.initial_cash
    cash = config.initial_cash
    equity_curve: list[dict] = []
    trades: list[TrendTrade] = []
    selected: list[str] = list(signal_by_sym.keys())[: config.top_n_assets]

    last_rebal_idx = -bars_per_rebalance  # force initial rebalance
    sharpe_lookback_bars = int(config.sharpe_lookback_days * rebal_periods_per_day)

    for bar_i, t in enumerate(all_idx):
        # Mark-to-market positions
        mtm_value = 0.0
        for sym in list(positions.keys()):
            df = ohlcv_by_symbol[sym]
            if t not in df.index:
                continue
            px = float(df.loc[t, "close"])
            pos = positions[sym]
            qty = pos["qty"]
            side_mul = 1.0 if pos["side"] == "long" else -1.0
            mtm_value += qty * px * side_mul + pos["entry_cash_reserved"]

            # Update trailing stop
            cur_atr = float(atr_by_sym[sym].get(t, np.nan))
            if not np.isnan(cur_atr):
                if pos["side"] == "long":
                    pos["hwm"] = max(pos["hwm"], px)
                    pos["trail_stop"] = pos["hwm"] - config.trailing_stop_atr_mult * cur_atr
                else:
                    pos["hwm"] = min(pos["hwm"], px)
                    pos["trail_stop"] = pos["hwm"] + config.trailing_stop_atr_mult * cur_atr

        # Check trailing stops + signal exits
        for sym in list(positions.keys()):
            df = ohlcv_by_symbol[sym]
            if t not in df.index:
                continue
            px = float(df.loc[t, "close"])
            pos = positions[sym]
            sig_now = float(signal_by_sym[sym].get(t, 0.0))

            exit_reason = None
            if pos["side"] == "long":
                if px <= pos["trail_stop"]:
                    exit_reason = "trailing_stop"
                elif sig_now <= -0.2:
                    exit_reason = "signal"
            else:
                if px >= pos["trail_stop"]:
                    exit_reason = "trailing_stop"
                elif sig_now >= 0.2:
                    exit_reason = "signal"

            if exit_reason:
                _close_position(
                    sym, pos, t, px, cost_factor, trades, exit_reason
                )
                cash += pos["entry_cash_reserved"] + pos["realized_pnl"]
                del positions[sym]

        # Periodic rebalance — select top-N by rolling Sharpe + open new positions
        if bar_i - last_rebal_idx >= bars_per_rebalance:
            last_rebal_idx = bar_i
            # Rank symbols by rolling Sharpe ratio of returns
            scores = []
            for sym in signal_by_sym:
                df = ohlcv_by_symbol[sym]
                if t not in df.index:
                    continue
                end_pos = df.index.searchsorted(t)
                start_pos = max(0, end_pos - sharpe_lookback_bars)
                window = df["close"].iloc[start_pos:end_pos + 1]
                rets = window.pct_change().dropna()
                if len(rets) < 10 or rets.std() == 0:
                    continue
                sr = rets.mean() / rets.std() * np.sqrt(bppy)
                scores.append((sym, sr))
            scores.sort(key=lambda x: -x[1])
            selected = [s for s, _ in scores[: config.top_n_assets]]

            # Open new positions for symbols not yet held, based on signal
            n_new_slots = max(config.top_n_assets - len(positions), 0)
            for sym in selected:
                if sym in positions:
                    continue
                if n_new_slots <= 0:
                    break
                df = ohlcv_by_symbol[sym]
                if t not in df.index:
                    continue
                sig_now = float(signal_by_sym[sym].get(t, 0.0))
                if abs(sig_now) < 0.5:
                    continue  # weak/no signal
                side = "long" if sig_now > 0 else "short"
                # Asymmetric weight
                slot_alloc = (config.long_weight if side == "long" else config.short_weight) / max(
                    config.top_n_assets, 1
                )
                vol_w = float(vol_w_by_sym[sym].get(t, 0.0))
                if vol_w <= 0:
                    continue
                target_notional = equity * slot_alloc * vol_w
                if target_notional < 50:  # min size
                    continue
                px = float(df.loc[t, "close"])
                qty = target_notional / px
                if qty * px > cash:
                    continue  # not enough cash
                cur_atr = float(atr_by_sym[sym].get(t, np.nan))
                if np.isnan(cur_atr) or cur_atr <= 0:
                    continue
                entry_cost = qty * px * cost_factor
                cash -= (qty * px + entry_cost)
                positions[sym] = {
                    "side": side,
                    "qty": qty,
                    "entry_px": px,
                    "entry_t": t,
                    "entry_cash_reserved": qty * px,
                    "realized_pnl": -entry_cost,
                    "hwm": px,
                    "trail_stop": (
                        px - config.trailing_stop_atr_mult * cur_atr
                        if side == "long"
                        else px + config.trailing_stop_atr_mult * cur_atr
                    ),
                }
                n_new_slots -= 1

        # Compute equity
        position_value = 0.0
        for sym, pos in positions.items():
            df = ohlcv_by_symbol[sym]
            if t not in df.index:
                continue
            px = float(df.loc[t, "close"])
            if pos["side"] == "long":
                position_value += pos["qty"] * px
            else:
                # short: profit if px decreases
                position_value += pos["qty"] * (2 * pos["entry_px"] - px)
        equity = cash + position_value

        equity_curve.append(
            {
                "t": t,
                "equity": float(equity),
                "exposure_pct": float(min(1.0, position_value / max(equity, 1))),
                "n_positions": len(positions),
            }
        )

    # Force close remaining positions at last bar
    last_t = all_idx[-1]
    for sym, pos in list(positions.items()):
        df = ohlcv_by_symbol[sym]
        if last_t not in df.index:
            continue
        px = float(df.loc[last_t, "close"])
        _close_position(sym, pos, last_t, px, cost_factor, trades, "end_of_period")
        cash += pos["entry_cash_reserved"] + pos["realized_pnl"]

    # Metrics
    eq_series = pd.Series([p["equity"] for p in equity_curve], index=[p["t"] for p in equity_curve])
    returns = eq_series.pct_change().dropna()
    sharpe = 0.0
    sortino = 0.0
    if len(returns) > 5 and returns.std() > 0:
        sharpe = float(returns.mean() / returns.std() * np.sqrt(bppy))
        downside = returns[returns < 0]
        if len(downside) > 0 and downside.std() > 0:
            sortino = float(returns.mean() / downside.std() * np.sqrt(bppy))

    peak = eq_series.cummax()
    dd = (eq_series - peak) / peak
    max_dd = float(dd.min()) if len(dd) > 0 else 0.0

    final_equity = float(eq_series.iloc[-1]) if len(eq_series) else config.initial_cash
    total_return = (final_equity - config.initial_cash) / config.initial_cash

    n_long = sum(1 for t in trades if t.side == "long")
    n_short = sum(1 for t in trades if t.side == "short")
    wins = sum(1 for t in trades if t.pnl > 0)
    win_rate = wins / max(len(trades), 1)
    avg_pnl_pct = float(np.mean([t.pnl_pct for t in trades])) if trades else 0.0

    # Monthly returns
    monthly = []
    if len(eq_series) > 0:
        eq_m = eq_series.resample("ME").last().pct_change().dropna()
        for ts, ret in eq_m.items():
            n_t = sum(1 for t in trades if t.exit_time.year == ts.year and t.exit_time.month == ts.month)
            monthly.append({"month": ts.strftime("%Y-%m"), "return_pct": float(ret * 100), "n_trades": n_t})

    # Per-asset stats
    per_asset: list[dict] = []
    seen = set()
    for tr in trades:
        if tr.symbol in seen:
            continue
        seen.add(tr.symbol)
        sym_trades = [t for t in trades if t.symbol == tr.symbol]
        per_asset.append({
            "symbol": tr.symbol,
            "n_trades": len(sym_trades),
            "n_winners": sum(1 for t in sym_trades if t.pnl > 0),
            "total_pnl": float(sum(t.pnl for t in sym_trades)),
            "avg_pnl_pct": float(np.mean([t.pnl_pct for t in sym_trades])),
        })

    return TrendResult(
        config=config,
        start_date=all_idx[0] if all_idx else datetime.now(timezone.utc),
        end_date=all_idx[-1] if all_idx else datetime.now(timezone.utc),
        n_trades=len(trades),
        n_long_trades=n_long,
        n_short_trades=n_short,
        initial_cash=config.initial_cash,
        final_equity=final_equity,
        total_return=total_return,
        sharpe=sharpe,
        sortino=sortino,
        max_drawdown=max_dd,
        win_rate=win_rate,
        avg_pnl_pct=avg_pnl_pct,
        monthly_returns=monthly,
        equity_curve=equity_curve,
        trades=trades,
        per_asset_stats=sorted(per_asset, key=lambda x: -x["total_pnl"]),
    )


def _close_position(
    sym: str,
    pos: dict,
    t: datetime,
    px: float,
    cost_factor: float,
    trades: list[TrendTrade],
    reason: str,
) -> None:
    qty = pos["qty"]
    entry_px = pos["entry_px"]
    side = pos["side"]
    exit_cost = qty * px * cost_factor
    if side == "long":
        gross = qty * (px - entry_px)
    else:
        gross = qty * (entry_px - px)
    net = gross - exit_cost + pos["realized_pnl"]  # realized_pnl already has entry cost
    pos["realized_pnl"] = net
    holding = (t - pos["entry_t"]).total_seconds() / 86400.0
    pnl_pct = net / (qty * entry_px) if entry_px > 0 else 0.0
    trades.append(
        TrendTrade(
            symbol=sym,
            side=side,
            entry_time=pos["entry_t"],
            entry_price=entry_px,
            exit_time=t,
            exit_price=px,
            pnl=net,
            pnl_pct=float(pnl_pct),
            holding_days=float(holding),
            reason=reason,
        )
    )
