"""Backtest engine per Cash-and-Carry funding arbitrage.

Real implementazione market-neutral pairs trade. Niente mock, niente stub.

Posizione:
    Quando in_position == True:
        coins_long_spot = N  (acquistati al prezzo spot entry)
        coins_short_perp = N (shortati al prezzo perp entry)
    P&L per ogni periodo:
        - delta spot:  N × (close_spot - prev_close_spot)  
        - delta perp: -N × (close_perp - prev_close_perp)  (short P&L)
        - funding:    -N × close_perp × funding_rate (short paga/riceve funding)
        -> in pratica delta_spot ≈ delta_perp se basis è stretto → si
           cancellano; resta solo funding × notional come carry.

Fee model:
    - entry: fee_spot + fee_perp = 2 × fee_taker
    - exit:  fee_spot + fee_perp = 2 × fee_taker
    Default fee_taker = 4 bps (Binance VIP0)

Triggers:
    entry: funding_rate > entry_threshold per N stacchi consecutivi
    exit:  funding_rate < exit_threshold per M stacchi consecutivi
            OR drawdown > max_dd (kill switch)

NOTA: in absence of perpetual price data (only mark price from funding),
usiamo spot price come proxy per perp entry/exit. Il basis cash-perp è
tipicamente < 0.1% in BTC, quindi assumption è ragionevole. Per migliorare:
ingestire klines spot + perp separati ma per ora questa è la baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class CarryConfig:
    symbol: str = "BTC/USDT"
    initial_cash: float = 10_000.0
    fee_taker: float = 0.0004  # 4 bps Binance VIP0
    slippage_bps: float = 2.0

    # Triggers
    entry_threshold: float = 0.0001   # 0.01% per 8h ≈ 0.11% APR
    exit_threshold: float = 0.00005   # 0.005% per 8h ≈ 0.055% APR
    consecutive_entry: int = 3        # 3 stacchi consecutivi sopra threshold
    consecutive_exit: int = 3

    # Position sizing
    position_fraction: float = 0.5    # 50% del cash in cash-and-carry (resto in cash)

    # Kill switch (anomalia liquidations o decoupling)
    max_drawdown_pct: float = -0.05   # -5% kill


@dataclass
class CarryTrade:
    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    notional: float
    coins: float
    funding_collected: float = 0.0
    n_funding_periods: int = 0
    fees_paid: float = 0.0
    pnl: float = 0.0


@dataclass
class CarryResult:
    symbol: str
    n_funding_periods: int
    n_trades: int
    total_funding_collected: float
    total_fees_paid: float
    final_equity: float
    total_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    apr: float  # annualized return
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)


def run_cash_and_carry(
    df_spot: pd.DataFrame,
    df_funding: pd.DataFrame,
    config: CarryConfig,
) -> CarryResult:
    """Backtest cash-and-carry su (df_spot, df_funding).

    Args:
        df_spot: DataFrame OHLCV con index=timestamp, colonna 'close' del SPOT.
            Idealmente 4h o 8h (per allineare con funding stacks 8h).
        df_funding: DataFrame con index=funding_time (8h stacchi), colonna 'funding_rate'.
        config: parametri.

    Returns:
        CarryResult con tutte le metriche.
    """
    if df_spot is None or df_spot.empty or df_funding is None or df_funding.empty:
        return _empty_result(config.symbol, config.initial_cash)

    # Allinea funding ai timestamp spot: per ogni candle spot, qual è il funding
    # in vigore in quel momento (ultimo stacco <= timestamp)?
    df = df_spot[["close"]].copy()
    df["funding_rate"] = df_funding["funding_rate"].reindex(df.index, method="ffill").fillna(0.0)

    # State
    cash = float(config.initial_cash)
    in_position = False
    coins = 0.0
    entry_price = 0.0
    consecutive_above = 0
    consecutive_below = 0
    funding_collected_trade = 0.0
    fees_paid_trade = 0.0
    n_funding_in_trade = 0
    entry_time = None
    last_funding_time = None
    trades: list[CarryTrade] = []
    equity_curve: list[dict[str, Any]] = []

    fee_total_oneway = config.fee_taker + config.slippage_bps / 10_000.0

    for ts, row in df.iterrows():
        price = float(row["close"])
        fr = float(row["funding_rate"])

        # 1) Mark to market position (delta-neutral so spot+short_perp ≈ 0,
        #    real P&L viene da funding accumulato + basis residuo).
        #    Approximation: ignoriamo il basis (assunzione spot ≈ perp).
        position_mark = coins * price if in_position else 0.0
        equity_now = cash + funding_collected_trade  # carry collected ma non realizzato

        # 2) Check stacco funding (every 8h): se il timestamp corrente
        #    cade su un nuovo stacco di funding, accumula carry
        is_new_funding_stack = False
        if ts in df_funding.index:
            is_new_funding_stack = True
        elif last_funding_time is None:
            is_new_funding_stack = True
        else:
            # se è passato >= 8h dal last_funding_time
            delta_s = (ts - last_funding_time).total_seconds()
            if delta_s >= 8 * 3600:
                is_new_funding_stack = True

        if is_new_funding_stack and in_position:
            carry = coins * price * fr
            funding_collected_trade += carry
            n_funding_in_trade += 1
            last_funding_time = ts
        elif is_new_funding_stack:
            last_funding_time = ts

        # 3) Update consecutive counters (regardless of position)
        if fr > config.entry_threshold:
            consecutive_above += 1
            consecutive_below = 0
        elif fr < config.exit_threshold:
            consecutive_below += 1
            consecutive_above = 0
        else:
            # neutral zone — reset both
            consecutive_above = max(0, consecutive_above - 1)
            consecutive_below = max(0, consecutive_below - 1)

        # 4) Entry logic
        if not in_position and consecutive_above >= config.consecutive_entry:
            notional = cash * config.position_fraction
            if notional > 1.0:
                # Apri pairs trade: long spot, short perp (assumiamo equal price)
                fee_entry = notional * fee_total_oneway * 2  # 2 leg
                coins = notional / price
                cash -= fee_entry
                entry_price = price
                entry_time = ts
                fees_paid_trade = fee_entry
                funding_collected_trade = 0.0
                n_funding_in_trade = 0
                in_position = True

        # 5) Exit logic
        if in_position and consecutive_below >= config.consecutive_exit:
            # Chiudi entrambe le gambe: assume basis = 0, P&L diretto = funding - fees
            notional_exit = coins * price
            fee_exit = notional_exit * fee_total_oneway * 2
            pnl = funding_collected_trade - fees_paid_trade - fee_exit
            cash += pnl
            trades.append(CarryTrade(
                entry_time=entry_time, exit_time=ts,
                entry_price=entry_price, exit_price=price,
                notional=coins * entry_price, coins=coins,
                funding_collected=funding_collected_trade,
                n_funding_periods=n_funding_in_trade,
                fees_paid=fees_paid_trade + fee_exit,
                pnl=pnl,
            ))
            coins = 0.0
            in_position = False
            funding_collected_trade = 0.0
            fees_paid_trade = 0.0
            n_funding_in_trade = 0

        # 6) Kill switch: drawdown vs peak equity
        peak_equity = max([e["equity"] for e in equity_curve] + [cash])
        dd = (equity_now / peak_equity - 1.0) if peak_equity > 0 else 0.0
        if in_position and dd < config.max_drawdown_pct:
            # Force exit
            notional_exit = coins * price
            fee_exit = notional_exit * fee_total_oneway * 2
            pnl = funding_collected_trade - fees_paid_trade - fee_exit
            cash += pnl
            trades.append(CarryTrade(
                entry_time=entry_time, exit_time=ts,
                entry_price=entry_price, exit_price=price,
                notional=coins * entry_price, coins=coins,
                funding_collected=funding_collected_trade,
                n_funding_periods=n_funding_in_trade,
                fees_paid=fees_paid_trade + fee_exit,
                pnl=pnl,
            ))
            coins = 0.0
            in_position = False
            funding_collected_trade = 0.0
            fees_paid_trade = 0.0
            n_funding_in_trade = 0
            consecutive_above = 0
            consecutive_below = 0

        # 7) Record equity snapshot
        equity_curve.append({
            "t": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "equity": cash + funding_collected_trade,
            "in_position": in_position,
            "funding_rate": fr,
        })

    # Final close if still in position
    if in_position:
        last_price = float(df["close"].iloc[-1])
        notional_exit = coins * last_price
        fee_exit = notional_exit * fee_total_oneway * 2
        pnl = funding_collected_trade - fees_paid_trade - fee_exit
        cash += pnl
        trades.append(CarryTrade(
            entry_time=entry_time, exit_time=df.index[-1],
            entry_price=entry_price, exit_price=last_price,
            notional=coins * entry_price, coins=coins,
            funding_collected=funding_collected_trade,
            n_funding_periods=n_funding_in_trade,
            fees_paid=fees_paid_trade + fee_exit,
            pnl=pnl,
        ))

    # Metriche finali
    final_eq = cash
    total_return = final_eq / config.initial_cash - 1.0
    n_trades = len(trades)
    n_winning = sum(1 for t in trades if t.pnl > 0)
    win_rate = (n_winning / n_trades) if n_trades > 0 else 0.0
    total_funding = sum(t.funding_collected for t in trades)
    total_fees = sum(t.fees_paid for t in trades)
    n_funding_periods = sum(t.n_funding_periods for t in trades)

    # Sharpe: returns per periodo
    eq_arr = np.array([e["equity"] for e in equity_curve])
    if len(eq_arr) >= 2:
        rets = np.diff(eq_arr) / np.where(eq_arr[:-1] > 0, eq_arr[:-1], 1.0)
        if rets.std() > 0:
            # Annualize using 6 bars per day for 4h candles (else fallback)
            periods_per_year = 365 * 6  # 4h = 6 per giorno
            sharpe = float(rets.mean() / rets.std() * np.sqrt(periods_per_year))
        else:
            sharpe = 0.0
        peak = np.maximum.accumulate(eq_arr)
        max_dd = float((eq_arr / peak - 1.0).min())
    else:
        sharpe = 0.0
        max_dd = 0.0

    # APR — assume periodo backtestato
    if len(df) >= 2:
        days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
        apr = (final_eq / config.initial_cash - 1.0) * (365.0 / max(days, 1.0))
    else:
        apr = 0.0

    return CarryResult(
        symbol=config.symbol,
        n_funding_periods=n_funding_periods,
        n_trades=n_trades,
        total_funding_collected=total_funding,
        total_fees_paid=total_fees,
        final_equity=final_eq,
        total_return=total_return,
        sharpe=sharpe,
        max_drawdown=max_dd,
        win_rate=win_rate,
        apr=apr,
        equity_curve=equity_curve,
        trades=[{
            "entry_time": t.entry_time.isoformat() if t.entry_time else None,
            "exit_time": t.exit_time.isoformat() if t.exit_time else None,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "notional": t.notional,
            "funding_collected": t.funding_collected,
            "n_funding_periods": t.n_funding_periods,
            "fees_paid": t.fees_paid,
            "pnl": t.pnl,
            "pnl_pct": t.pnl / max(t.notional, 1e-9),
        } for t in trades],
    )


def _empty_result(symbol: str, initial_cash: float) -> CarryResult:
    return CarryResult(
        symbol=symbol, n_funding_periods=0, n_trades=0,
        total_funding_collected=0.0, total_fees_paid=0.0,
        final_equity=initial_cash, total_return=0.0, sharpe=0.0,
        max_drawdown=0.0, win_rate=0.0, apr=0.0,
    )
