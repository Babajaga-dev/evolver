"""Backtest statico del Council: usato sia dall'evolver che da baselines."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.replay import council as council_mod


def backtest_council_static(
    *,
    candles_by_tf: dict[str, pd.DataFrame],
    regime_series: pd.Series,
    council: council_mod.CouncilParams,
    initial_cash: float = 10_000.0,
    fee: float = 0.0004,
    slippage_bps: float = 5.0,
) -> dict:
    """Backtest del Council sui candles_by_tf, ritorna metriche aggregate."""
    df_4h = candles_by_tf.get("4h")
    if df_4h is None or df_4h.empty or len(df_4h) < 30:
        return {"sharpe": 0.0, "max_drawdown": 0.0, "total_return": 0.0, "n_trades": 0, "final_equity": initial_cash}

    entries, exits, pos_pct = council_mod.compute_signals_hierarchical(
        candles_by_tf, council, regime_series
    )
    close = df_4h["close"].values
    n = len(close)
    equity = np.zeros(n)
    equity[0] = initial_cash
    cash = initial_cash
    coins = 0.0
    in_position = False
    n_trades = 0
    fee_total = fee + slippage_bps / 10_000.0
    pos_arr = pos_pct.values
    e_arr = entries.values
    x_arr = exits.values

    for i in range(1, n):
        price = close[i]
        if in_position and x_arr[i]:
            cash += coins * price * (1.0 - fee_total)  # ADD not REPLACE
            coins = 0.0
            in_position = False
            n_trades += 1
        elif not in_position and e_arr[i] and pos_arr[i] > 0:
            alloc = min(pos_arr[i] / 100.0, 1.0) * cash
            buy_cash = alloc * (1.0 - fee_total)
            coins = buy_cash / price
            cash -= alloc
            in_position = True
            n_trades += 1
        equity[i] = cash + coins * price

    returns = np.diff(equity) / equity[:-1]
    sharpe = (returns.mean() / returns.std() * np.sqrt(365 * 6)) if returns.std() > 0 else 0.0
    peak = np.maximum.accumulate(equity)
    dd = float(((equity / peak) - 1.0).min())
    total_return = float(equity[-1] / equity[0] - 1.0)
    return {
        "sharpe": float(sharpe),
        "max_drawdown": dd,
        "total_return": total_return,
        "n_trades": int(n_trades),
        "final_equity": float(equity[-1]),
    }
