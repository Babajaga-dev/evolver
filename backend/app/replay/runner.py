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


async def _fetch_funding_window(
    session, symbol: str, start: datetime, end: datetime
) -> pd.DataFrame:
    """Fetch funding rates. Returns df with funding_time index and funding_rate column.

    Funding viene da Binance USDS-M perpetual ogni 8h. Lo allineiamo
    forward-fill su candele 4h con merge.
    """
    from app.repositories import funding as funding_repo
    rows = await funding_repo.fetch_funding(session, symbol=symbol, start=start, end=end, limit=50000)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
        {"timestamp": r.funding_time, "funding_rate": float(r.funding_rate)} for r in rows
    ]).set_index("timestamp")


def _attach_funding_to_ohlcv(df_ohlcv: pd.DataFrame, df_funding: pd.DataFrame) -> pd.DataFrame:
    """Merge funding rate (8h freq) su candele 4h con forward-fill."""
    if df_funding is None or df_funding.empty or df_ohlcv is None or df_ohlcv.empty:
        out = df_ohlcv.copy() if df_ohlcv is not None else pd.DataFrame()
        if not out.empty:
            out["funding_rate"] = 0.0
        return out
    # Reindex funding on OHLCV index with forward-fill
    funding_aligned = df_funding["funding_rate"].reindex(df_ohlcv.index, method="ffill").fillna(0.0)
    out = df_ohlcv.copy()
    out["funding_rate"] = funding_aligned
    return out


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
    start_idx: int = 0,
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
        # Mark to market (always)
        equity[i] = cash + coins * price
        # Skip trades before start_idx (warmup region)
        if i < start_idx:
            continue

        if in_position and exits_arr[i]:
            cash += coins * price * (1.0 - fee_total)  # ADD not REPLACE
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
    iteration = 0

    try:
        while cursor < cfg.end_date:
            # 1. Check status flag (every chunk)
            async with session_scope() as s:
                r = await replay_repo.get_run(s, run_id)
                if r is None:
                    log.warning("replay.disappeared", run_id=str(run_id))
                    return
                if r.status in ("stopping", "cancelled"):
                    await replay_repo.update_status(s, run_id, "cancelled")
                    log.info("replay.stopped", run_id=str(run_id))
                    return

            # 2. Re-evolution check (kept identical)
            needs_retrain = (
                organism_params is None
                or last_retrain_t is None
                or (cursor - last_retrain_t).days >= cfg.retrain_cadence_days
            )
            # Kill switch: solo se abbiamo >= 60 bars (~10 giorni 4h) di storia
            # nel buffer, ALTRIMENTI il drawdown è troppo rumoroso da inizializzazione.
            # E nuovo cooldown: niente kill se l'ultimo retrain è < 7 giorni fa
            cooldown_ok = last_retrain_t is None or (cursor - last_retrain_t).days >= 7
            kill_triggered = (
                len(equity_buf) >= 60
                and cooldown_ok
                and _drawdown_window(equity_buf, cfg.kill_switch_window_days * 6)
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
                    df_fund_train = await _fetch_funding_window(s, cfg.symbol, train_start, cursor)
                # Attach funding to training 4h
                df_4h_train = _attach_funding_to_ohlcv(df_4h_train, df_fund_train)

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

            # 3. Chunk-based simulation: avanza al prossimo retrain (o end_date)
            chunk_end = min(cursor + timedelta(days=cfg.retrain_cadence_days), cfg.end_date)
            # Fetch dati nel chunk + warmup per indicatori (200 bars indietro)
            warmup_start = cursor - timedelta(days=40)
            async with session_scope() as s:
                df_4h_chunk = await _fetch_ohlcv_window(s, cfg.symbol, "4h", warmup_start, chunk_end)
                df_1h_chunk = await _fetch_ohlcv_window(s, cfg.symbol, "1h", warmup_start, chunk_end)
                df_1d_chunk = await _fetch_ohlcv_window(s, cfg.symbol, "1d", warmup_start - timedelta(days=40), chunk_end)
                df_funding = await _fetch_funding_window(s, cfg.symbol, warmup_start, chunk_end)
            # Merge funding rate into 4h dataframe (forward-fill 8h → 4h)
            df_4h_chunk = _attach_funding_to_ohlcv(df_4h_chunk, df_funding)

            if df_4h_chunk is None or df_4h_chunk.empty or len(df_4h_chunk) < 10:
                cursor = chunk_end
                continue
            if df_1d_chunk is None or df_1d_chunk.empty:
                regime_chunk = pd.Series("range", index=df_4h_chunk.index)
            else:
                try:
                    regime_chunk = await _detect_regime_series(df_1d_chunk)
                except Exception as exc:
                    log.warning("replay.regime_failed", error=str(exc))
                    regime_chunk = pd.Series("range", index=df_4h_chunk.index)
            if df_1h_chunk is None or df_1h_chunk.empty:
                df_1h_chunk = df_4h_chunk

            # Pre-compute cursor_idx (index nel df dove inizia il chunk)
            timestamps = df_4h_chunk.index
            cursor_idx = None
            for i, ts in enumerate(timestamps):
                if ts >= cursor:
                    cursor_idx = i
                    break
            if cursor_idx is None:
                cursor = chunk_end
                continue
            try:
                # Simula il chunk: backtest con start_idx = cursor_idx
                # (la warmup region è solo per gli indicatori, niente trade lì)
                sim = _compute_equity_and_drawdown(
                    df_4h=df_4h_chunk,
                    candles_by_tf={"1h": df_1h_chunk, "4h": df_4h_chunk, "1d": df_1d_chunk},
                    council_params=organism_params,
                    regime_series=regime_chunk,
                    initial_cash=cash,
                    fee=cfg.fee,
                    slippage_bps=cfg.slippage_bps,
                    start_idx=cursor_idx,
                )
            except Exception as exc:
                log.warning("replay.sim_failed", error=str(exc), cursor=cursor.isoformat())
                cursor = chunk_end
                continue

            equity_arr = sim["equity"]
            pos_arr = sim["position_size"]

            snapshot_rows: list[dict[str, Any]] = []
            for i in range(cursor_idx, len(equity_arr)):
                if (i - cursor_idx) % SNAPSHOT_EVERY_N_BARS != 0 and i != len(equity_arr) - 1:
                    continue
                eq = float(equity_arr[i])
                peak_so_far = float(max(equity_arr[: i + 1]))
                dd_now = (eq / peak_so_far - 1.0) * 100.0 if peak_so_far > 0 else 0.0
                reg_label = regime_chunk.iloc[min(i, len(regime_chunk) - 1)] if len(regime_chunk) else None
                ts = timestamps[i].to_pydatetime() if hasattr(timestamps[i], 'to_pydatetime') else timestamps[i]
                snapshot_rows.append({
                    "t": ts,
                    "equity": eq,
                    "position_size_pct": float(pos_arr[i]) if i < len(pos_arr) else 0.0,
                    "drawdown_pct": dd_now,
                    "regime": str(reg_label) if reg_label else None,
                    "active_strategy": "council",
                    "n_trades_so_far": int(sim["n_trades"]),
                })

            cash = float(equity_arr[-1])
            equity_buf.append(cash)
            iteration += 1

            # Persist snapshots + progress
            days_done = max((chunk_end - cfg.start_date).days, 0)
            pct = min(days_done / total_days * 100.0, 99.9)
            async with session_scope() as s:
                if snapshot_rows:
                    await replay_repo.append_equity_batch(s, replay_id=run_id, rows=snapshot_rows)
                await replay_repo.update_progress(
                    s, run_id,
                    current_simulated_date=chunk_end,
                    current_equity=cash,
                    progress_pct=pct,
                )

            cursor = chunk_end

        # 4. Fine: final metrics
        async with session_scope() as s:
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

        # Baseline 1 — Buy & Hold
        async with session_scope() as s:
            df_full = await _fetch_ohlcv_window(s, cfg.symbol, "4h", cfg.start_date, cfg.end_date)
            df_1h_full = await _fetch_ohlcv_window(s, cfg.symbol, "1h", cfg.start_date, cfg.end_date)
            df_1d_full = await _fetch_ohlcv_window(s, cfg.symbol, "1d", cfg.start_date - timedelta(days=40), cfg.end_date)
            df_fund_full = await _fetch_funding_window(s, cfg.symbol, cfg.start_date, cfg.end_date)
        df_full = _attach_funding_to_ohlcv(df_full, df_fund_full)
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

        # Baseline 2 — Textbook Council (params default, niente GA, regime detector standard)
        textbook_metrics = {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "final_equity": cfg.initial_cash}
        if not df_full.empty and len(df_full) > 50:
            try:
                from app.replay.runner_backtest import backtest_council_static
                from app.replay.council import default_council_params
                if df_1d_full is None or df_1d_full.empty:
                    regime_full = pd.Series("range", index=df_full.index)
                else:
                    regime_full = _detect_regime_series_local(df_1d_full)
                if df_1h_full is None or df_1h_full.empty:
                    df_1h_full = df_full
                tb_council = default_council_params()
                tb_r = backtest_council_static(
                    candles_by_tf={"1h": df_1h_full, "4h": df_full, "1d": df_1d_full},
                    regime_series=regime_full,
                    council=tb_council,
                    initial_cash=cfg.initial_cash,
                    fee=cfg.fee,
                    slippage_bps=cfg.slippage_bps,
                )
                textbook_metrics = {
                    "sharpe": float(tb_r.get("sharpe", 0.0)),
                    "total_return": float(tb_r.get("total_return", 0.0)),
                    "max_drawdown": float(tb_r.get("max_drawdown", 0.0)),
                    "final_equity": float(tb_r.get("final_equity", cfg.initial_cash)),
                    "n_trades": int(tb_r.get("n_trades", 0)),
                }
            except Exception as exc:
                log.warning("replay.baseline_textbook_failed", error=str(exc))

        # Baseline 3 — GA-one-shot: usa SOLO il primo organismo, niente re-evoluzione
        gaoneshot_metrics = {"sharpe": 0.0, "total_return": 0.0, "max_drawdown": 0.0, "final_equity": cfg.initial_cash}
        if not df_full.empty and len(df_full) > 50:
            try:
                async with session_scope() as s:
                    first_events = await replay_repo.get_retrain_events(s, run_id)
                if first_events:
                    from app.replay import genome as gn
                    first_chrom = first_events[0].organism.get("chromosome", {}) if isinstance(first_events[0].organism, dict) else {}
                    if first_chrom:
                        os_council = gn.decode_to_council(first_chrom)
                        if df_1d_full is None or df_1d_full.empty:
                            regime_full2 = pd.Series("range", index=df_full.index)
                        else:
                            regime_full2 = _detect_regime_series_local(df_1d_full)
                        os_r = backtest_council_static(
                            candles_by_tf={"1h": df_1h_full if df_1h_full is not None and not df_1h_full.empty else df_full, "4h": df_full, "1d": df_1d_full},
                            regime_series=regime_full2,
                            council=os_council,
                            initial_cash=cfg.initial_cash,
                            fee=cfg.fee,
                            slippage_bps=cfg.slippage_bps,
                        )
                        gaoneshot_metrics = {
                            "sharpe": float(os_r.get("sharpe", 0.0)),
                            "total_return": float(os_r.get("total_return", 0.0)),
                            "max_drawdown": float(os_r.get("max_drawdown", 0.0)),
                            "final_equity": float(os_r.get("final_equity", cfg.initial_cash)),
                            "n_trades": int(os_r.get("n_trades", 0)),
                        }
            except Exception as exc:
                log.warning("replay.baseline_gaoneshot_failed", error=str(exc))

        # Alpha vs baselines
        alpha_bh = float(sharpe - bh_sharpe)
        alpha_textbook = float(sharpe - textbook_metrics["sharpe"])
        alpha_gaoneshot = float(sharpe - gaoneshot_metrics["sharpe"])

        # Deflated Sharpe Ratio (Bailey & Lopez de Prado SSRN 2460551)
        n_trials_total = max(int(run.n_retrains * cfg.ga_pop_size * cfg.ga_generations), 2)
        try:
            from app.metrics.deflated_sharpe import deflated_sharpe_ratio
            dsr_info = deflated_sharpe_ratio(
                observed_sharpe=float(sharpe),
                returns=returns,
                n_trials=n_trials_total,
            )
        except Exception as exc:
            log.warning("replay.dsr_failed", error=str(exc))
            dsr_info = {"dsr": 0.5, "verdict": "computation_error"}

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
                },
                "textbook_council": textbook_metrics,
                "ga_one_shot": gaoneshot_metrics,
            },
            "alpha_vs_buy_hold": alpha_bh,
            "alpha_vs_textbook": alpha_textbook,
            "alpha_vs_ga_one_shot": alpha_gaoneshot,
            "deflated_sharpe": dsr_info,
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
