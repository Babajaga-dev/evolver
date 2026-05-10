"""ReplayRunner — orchestratore del replay storico con organismo adattivo.

Loop deterministico:
    cursor = start_date + warmup
    while cursor < end_date:
        if needs_retrain():
            evolve organism using rolling window [cursor - lookback, cursor]
            persist retrain event
        apply organism decision on next bar
        update equity
        check kill switch (DD 30d > -10%)
        every N bars: persist equity snapshot + heartbeat
        check 'stopping' status flag → exit gracefully
        cursor += primary_tf_step
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.core.db import session_scope
from app.core.logging import get_logger
from app.regime.detector import _classify, ADX_TREND_THRESHOLD, ATR_HIGH_VOL, SMA_SLOPE_LOOKBACK
from app.indicators.core import compute as compute_indicator
from app.repositories import ohlcv as ohlcv_repo
from app.replay import council as council_mod
from app.replay import genome as genome_mod
from app.replay import repo as replay_repo
from app.replay.evolver import evolve_council

log = get_logger(__name__)


# Costanti default
DEFAULT_PRIMARY_TF = "4h"
PRIMARY_TF_MS = 4 * 3600 * 1000
SNAPSHOT_EVERY_N_BARS = 6  # ~ ogni giorno su 4h
HEARTBEAT_EVERY_N_BARS = 24  # ~ ogni 4 giorni


@dataclass
class ReplayConfig:
    start_date: datetime
    end_date: datetime
    symbol: str = "BTC/USDT"
    initial_cash: float = 10_000.0
    retrain_cadence_days: int = 14
    lookback_days: int = 180
    kill_switch_dd_pct: float = -10.0  # -10% in 30d
    kill_switch_window_days: int = 30
    ga_pop_size: int = 20
    ga_generations: int = 8
    fee: float = 0.0004
    slippage_bps: float = 5.0


async def _fetch_ohlcv_window(
    session, symbol: str, tf: str, start: datetime, end: datetime
) -> pd.DataFrame:
    rows = await ohlcv_repo.fetch_ohlcv(session, symbol=symbol, timeframe=tf, start=start, end=end, limit=50000)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([{
        "timestamp": r.timestamp,
        "open": float(r.open),
        "high": float(r.high),
        "low": float(r.low),
        "close": float(r.close),
        "volume": float(r.volume),
    } for r in rows])
    return df.set_index("timestamp")


def _detect_regime_series_local(df_1d: pd.DataFrame) -> pd.Series:
    """Etichetta regime per ogni timestamp in df_1d. Versione locale (no DB).

    Computa ADX/ATR/SMA50/RSI sull'INTERA serie una volta sola, poi per ogni
    bar i applica _classify usando i valori a quel momento. Stripped-down
    rispetto a app.regime.detector.detect_regime (che lavora su un solo "now"
    e fetcha da DB).
    """
    if df_1d.empty or len(df_1d) < 30:
        return pd.Series("range", index=df_1d.index)
    try:
        adx_out, _ = compute_indicator("adx", df_1d, {"period": 14})
        atr_out, _ = compute_indicator("atr", df_1d, {"period": 14})
        sma_out, _ = compute_indicator("sma", df_1d, {"period": 50})
        rsi_out, _ = compute_indicator("rsi", df_1d, {"period": 14})
    except Exception:
        return pd.Series("range", index=df_1d.index)

    adx = adx_out["adx"].fillna(0.0)
    atr = atr_out["atr"].fillna(0.0)
    sma = sma_out["sma"]
    rsi = rsi_out["rsi"].fillna(50.0)
    close = df_1d["close"]

    labels: list[str] = []
    for i in range(len(df_1d)):
        last_adx = float(adx.iloc[i])
        last_close = float(close.iloc[i])
        last_atr = float(atr.iloc[i])
        atr_pct = (last_atr / last_close * 100) if last_close > 0 else 0.0
        # SMA slope
        if i >= SMA_SLOPE_LOOKBACK and not pd.isna(sma.iloc[i]) and not pd.isna(sma.iloc[i - SMA_SLOPE_LOOKBACK]):
            sma_now = float(sma.iloc[i])
            sma_prev = float(sma.iloc[i - SMA_SLOPE_LOOKBACK])
            sma_slope = ((sma_now - sma_prev) / sma_prev * 100) if sma_prev > 0 else 0.0
        else:
            sma_slope = 0.0
        last_rsi = float(rsi.iloc[i])
        try:
            regime, _conf, _notes = _classify(
                adx=last_adx, atr_pct=atr_pct,
                sma_slope_pct=sma_slope, rsi=last_rsi,
            )
        except Exception:
            regime = "range"
        labels.append(regime)
    return pd.Series(labels, index=df_1d.index)


async def _detect_regime_series(df_1d: pd.DataFrame) -> pd.Series:
    """Wrapper async per coerenza con altri await in runner."""
    return _detect_regime_series_local(df_1d)


def _compute_equity_and_drawdown(
    df_4h: pd.DataFrame,
    candles_by_tf: dict[str, pd.DataFrame],
    council_params,
    regime_series: pd.Series,
    initial_cash: float,
    fee: float,
    slippage_bps: float,
) -> dict[str, np.ndarray | float]:
    """Backtest del Council sul df_4h dato.

    Ritorna: equity, position_size_pct array allineato all'index di df_4h,
    drawdown, total trades.
    """
    entries, exits, pos_pct = council_mod.compute_signals_hierarchical(
        candles_by_tf, council_params, regime_series
    )
    close = df_4h["close"].values
    n = len(close)
    if n < 2:
        return {
            "equity": np.array([initial_cash]),
            "position_size": np.zeros(1),
            "drawdown": np.zeros(1),
            "n_trades": 0,
            "final_equity": initial_cash,
        }
    equity = np.zeros(n)
    equity[0] = initial_cash
    cash = initial_cash
    coins = 0.0
    in_position = False
    n_trades = 0
    fee_total = fee + slippage_bps / 10_000.0
    pos_pct_arr = pos_pct.values
    entries_arr = entries.values
    exits_arr = exits.values

    for i in range(1, n):
        price = close[i]
        # Mark to market
        equity[i] = cash + coins * price

        if in_position and exits_arr[i]:
            cash = coins * price * (1.0 - fee_total)
            coins = 0.0
            in_position = False
            n_trades += 1
        elif not in_position and entries_arr[i] and pos_pct_arr[i] > 0:
            alloc = min(pos_pct_arr[i] / 100.0, 1.0) * cash
            buy_cash = alloc * (1.0 - fee_total)
            coins = buy_cash / price
            cash = cash - alloc
            in_position = True
            n_trades += 1
        equity[i] = cash + coins * price

    peak = np.maximum.accumulate(equity)
    drawdown = (equity / peak) - 1.0
    return {
        "equity": equity,
        "position_size": pos_pct_arr,
        "drawdown": drawdown,
        "n_trades": int(n_trades),
        "final_equity": float(equity[-1]),
    }


def _drawdown_window(equity_buf: list[float], window: int) -> float:
    if len(equity_buf) < 2:
        return 0.0
    sub = equity_buf[-window:] if len(equity_buf) >= window else equity_buf
    peak = max(sub)
    if peak <= 0:
        return 0.0
    return (sub[-1] / peak - 1.0) * 100.0


async def run_replay_task(run_id: uuid.UUID) -> None:
    """Esegue un replay completo. Idempotente: legge stato corrente e riprende.

    Lanciato come asyncio.create_task() da endpoint /api/v1/replay/start
    o all'avvio app per i run con status pending/running.
    """
    async with session_scope() as session:
        run = await replay_repo.get_run(session, run_id)
        if run is None:
            log.warning("replay.run_not_found", run_id=str(run_id))
            return
        if run.status in ("completed", "cancelled", "failed"):
            log.info("replay.skip_terminal", run_id=str(run_id), status=run.status)
            return

        cfg_raw = dict(run.config)
        cfg = ReplayConfig(
            start_date=datetime.fromisoformat(cfg_raw["start_date"]) if isinstance(cfg_raw["start_date"], str) else cfg_raw["start_date"],
            end_date=datetime.fromisoformat(cfg_raw["end_date"]) if isinstance(cfg_raw["end_date"], str) else cfg_raw["end_date"],
            symbol=cfg_raw.get("symbol", "BTC/USDT"),
            initial_cash=float(cfg_raw.get("initial_cash", 10_000.0)),
            retrain_cadence_days=int(cfg_raw.get("retrain_cadence_days", 14)),
            lookback_days=int(cfg_raw.get("lookback_days", 180)),
            kill_switch_dd_pct=float(cfg_raw.get("kill_switch_dd_pct", -10.0)),
            kill_switch_window_days=int(cfg_raw.get("kill_switch_window_days", 30)),
            ga_pop_size=int(cfg_raw.get("ga_pop_size", 20)),
            ga_generations=int(cfg_raw.get("ga_generations", 8)),
            fee=float(cfg_raw.get("fee", 0.0004)),
            slippage_bps=float(cfg_raw.get("slippage_bps", 5.0)),
        )

        # Resume: trova ultima data simulata
        cursor = run.current_simulated_date
        if cursor is None:
            cursor = cfg.start_date
            if cursor.tzinfo is None:
                cursor = cursor.replace(tzinfo=timezone.utc)
        cash = run.current_equity if run.current_equity > 0 else cfg.initial_cash
        last_retrain_t: datetime | None = None
        organism_params = None
        equity_buf: list[float] = [cash]

        await replay_repo.update_status(session, run_id, "running")
        log.info("replay.start", run_id=str(run_id), cursor=cursor.isoformat(), end=cfg.end_date.isoformat())

    total_days = max((cfg.end_date - cfg.start_date).days, 1)
    snapshot_buffer: list[dict[str, Any]] = []
    iteration = 0

    try:
        while cursor < cfg.end_date:
            # 1. Check status flag
            async with session_scope() as s:
                r = await replay_repo.get_run(s, run_id)
                if r is None:
                    log.warning("replay.disappeared", run_id=str(run_id))
                    return
                if r.status in ("stopping", "cancelled"):
                    await replay_repo.update_status(s, run_id, "cancelled")
                    log.info("replay.stopped", run_id=str(run_id))
                    return

            # 2. Re-evolution check
            needs_retrain = (
                organism_params is None
                or last_retrain_t is None
                or (cursor - last_retrain_t).days >= cfg.retrain_cadence_days
            )
            kill_triggered = (
                _drawdown_window(equity_buf, cfg.kill_switch_window_days * 6)
                < cfg.kill_switch_dd_pct
            )
            if kill_triggered:
                needs_retrain = True

            if needs_retrain:
                lookback = (
                    cfg.lookback_days * 2 if kill_triggered else cfg.lookback_days
                )
                train_start = cursor - timedelta(days=lookback)
                t0 = datetime.now(timezone.utc)
                async with session_scope() as s:
                    df_4h_train = await _fetch_ohlcv_window(
                        s, cfg.symbol, "4h", train_start, cursor
                    )
                    df_1h_train = await _fetch_ohlcv_window(
                        s, cfg.symbol, "1h", train_start, cursor
                    )
                    df_1d_train = await _fetch_ohlcv_window(
                        s, cfg.symbol, "1d", train_start, cursor
                    )

                if len(df_4h_train) < 50:
                    # Non c'è abbastanza dato, salta al prossimo bar e riprova
                    log.warning(
                        "replay.insufficient_train",
                        cursor=cursor.isoformat(),
                        n=len(df_4h_train),
                    )
                    cursor += timedelta(hours=4)
                    continue

                regime_series_train = await _detect_regime_series(df_1d_train)

                try:
                    organism_params, train_metrics = await evolve_council(
                        candles_by_tf={"1h": df_1h_train, "4h": df_4h_train, "1d": df_1d_train},
                        regime_series=regime_series_train,
                        pop_size=cfg.ga_pop_size,
                        generations=cfg.ga_generations,
                        initial_cash=cfg.initial_cash,
                        fee=cfg.fee,
                        slippage_bps=cfg.slippage_bps,
                    )
                except Exception as exc:
                    log.warning("replay.evolve_failed", error=str(exc), cursor=cursor.isoformat())
                    # Fallback: textbook council
                    organism_params = council_mod.default_council_params()
                    train_metrics = {"sharpe_train": 0.0, "max_dd_train": 0.0, "diversity": 0.0, "n_trades_train": 0}

                elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
                trigger = "kill_switch" if kill_triggered else ("initial" if last_retrain_t is None else "scheduled")
                async with session_scope() as s:
                    await replay_repo.append_retrain_event(
                        s,
                        replay_id=run_id,
                        t=cursor,
                        trigger=trigger,
                        organism={
                            "chromosome": genome_mod.encode_from_council(organism_params),
                            **train_metrics,
                        },
                        elapsed_seconds=elapsed,
                        equity_at_retrain=cash,
                    )
                last_retrain_t = cursor
                log.info(
                    "replay.retrained",
                    cursor=cursor.isoformat(),
                    trigger=trigger,
                    elapsed=elapsed,
                    sharpe=train_metrics.get("sharpe_train"),
                )

            # 3. Avanza di 1 candela 4h: simula la decisione per il prossimo bar
            step_end = cursor + timedelta(hours=4)
            # Pre-warm window per indicatori (60 candele indietro = ~10 giorni 4h)
            recent_start = cursor - timedelta(days=20)
            async with session_scope() as s:
                df_4h_now = await _fetch_ohlcv_window(s, cfg.symbol, "4h", recent_start, step_end)
                df_1h_now = await _fetch_ohlcv_window(s, cfg.symbol, "1h", recent_start, step_end)
                df_1d_now = await _fetch_ohlcv_window(s, cfg.symbol, "1d", recent_start - timedelta(days=20), step_end)

            if df_4h_now is None or df_4h_now.empty or len(df_4h_now) < 2:
                # Dati assenti, avanza e riprova
                cursor = step_end
                continue
            if df_1d_now is None or df_1d_now.empty:
                regime_now = pd.Series("range", index=df_4h_now.index)
            else:
                try:
                    regime_now = await _detect_regime_series(df_1d_now)
                except Exception as exc:
                    log.warning("replay.regime_failed", error=str(exc))
                    regime_now = pd.Series("range", index=df_4h_now.index)
            if df_1h_now is None or df_1h_now.empty:
                df_1h_now = df_4h_now  # fallback: use 4h candles as 1h surrogate
            try:
                sim = _compute_equity_and_drawdown(
                df_4h=df_4h_now,
                candles_by_tf={"1h": df_1h_now, "4h": df_4h_now, "1d": df_1d_now},
                council_params=organism_params,
                regime_series=regime_now,
                initial_cash=cash,
                fee=cfg.fee,
                slippage_bps=cfg.slippage_bps,
                )
            except Exception as exc:
                log.warning("replay.sim_failed", error=str(exc), cursor=cursor.isoformat())
                cursor = step_end
                continue

            # Aggiorna equity con l'ULTIMO bar simulato (rolling step)
            final_equity = sim["final_equity"]
            equity_buf.append(final_equity)
            cash = final_equity
            iteration += 1

            # Snapshot ogni N bars
            if iteration % SNAPSHOT_EVERY_N_BARS == 0 or cursor + timedelta(hours=4) >= cfg.end_date:
                peak = max(equity_buf)
                dd = (final_equity / peak - 1.0) * 100.0 if peak > 0 else 0.0
                # Last regime label
                last_regime = regime_now.iloc[-1] if len(regime_now) else None
                snapshot_buffer.append({
                    "t": step_end,
                    "equity": final_equity,
                    "position_size_pct": float(sim["position_size"][-1]) if len(sim["position_size"]) else 0.0,
                    "drawdown_pct": dd,
                    "regime": str(last_regime) if last_regime else None,
                    "active_strategy": "council",
                    "n_trades_so_far": int(sim["n_trades"]),
                })

            # Heartbeat + flush snapshots ogni N bars
            if iteration % HEARTBEAT_EVERY_N_BARS == 0:
                days_done = max((cursor - cfg.start_date).days, 0)
                pct = min(days_done / total_days * 100.0, 99.9)
                async with session_scope() as s:
                    if snapshot_buffer:
                        await replay_repo.append_equity_batch(s, replay_id=run_id, rows=snapshot_buffer)
                        snapshot_buffer = []
                    await replay_repo.update_progress(
                        s,
                        run_id,
                        current_simulated_date=cursor,
                        current_equity=cash,
                        progress_pct=pct,
                    )

            cursor = step_end

        # 4. Fine: flush + final metrics
        async with session_scope() as s:
            if snapshot_buffer:
                await replay_repo.append_equity_batch(s, replay_id=run_id, rows=snapshot_buffer)
            await replay_repo.update_progress(
                s, run_id,
                current_simulated_date=cursor,
                current_equity=cash,
                progress_pct=99.9,
            )
            snapshots = await replay_repo.get_equity_snapshots(s, run_id, limit=100_000)

        equity_series = np.array([float(sn.equity) for sn in snapshots]) if snapshots else np.array([cfg.initial_cash, cash])
        returns = np.diff(equity_series) / equity_series[:-1] if len(equity_series) > 1 else np.array([0.0])
        sharpe = (returns.mean() / returns.std() * np.sqrt(365 * 6)) if returns.std() > 0 else 0.0
        peak = np.maximum.accumulate(equity_series)
        dd = ((equity_series / peak) - 1.0).min()
        total_return = (equity_series[-1] / equity_series[0]) - 1.0

        # Baseline buy & hold
        async with session_scope() as s:
            df_full = await _fetch_ohlcv_window(s, cfg.symbol, "4h", cfg.start_date, cfg.end_date)
        if not df_full.empty:
            bh_ret = (df_full["close"].iloc[-1] / df_full["close"].iloc[0]) - 1.0
            bh_equity = df_full["close"] / df_full["close"].iloc[0] * cfg.initial_cash
            bh_peak = bh_equity.cummax()
            bh_dd = ((bh_equity / bh_peak) - 1.0).min()
            bh_returns = bh_equity.pct_change().dropna()
            bh_sharpe = bh_returns.mean() / bh_returns.std() * np.sqrt(365 * 6) if bh_returns.std() > 0 else 0.0
        else:
            bh_ret = 0.0
            bh_dd = 0.0
            bh_sharpe = 0.0

        final_metrics = {
            "sharpe": float(sharpe),
            "total_return": float(total_return),
            "max_drawdown": float(dd),
            "final_equity": float(cash),
            "n_retrains": run.n_retrains,
            "baselines": {
                "buy_hold": {
                    "sharpe": float(bh_sharpe),
                    "total_return": float(bh_ret),
                    "max_drawdown": float(bh_dd),
                }
            }
        }
        async with session_scope() as s:
            await replay_repo.set_final_metrics(s, run_id, final_metrics=final_metrics)
        log.info("replay.completed", run_id=str(run_id), sharpe=sharpe, total_return=total_return, bh_return=bh_ret)

    except Exception as exc:
        log.exception("replay.failed", run_id=str(run_id), error=str(exc))
        async with session_scope() as s:
            await replay_repo.update_status(s, run_id, "failed", error=str(exc)[:2000])


class ReplayRunner:
    """Helper class — wrap di run_replay_task per usi futuri."""

    @staticmethod
    async def start(run_id: uuid.UUID) -> asyncio.Task:
        return asyncio.create_task(run_replay_task(run_id))
