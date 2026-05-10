"""Paper trading engine — simulazione tick-by-tick.

Pipeline:
    1. Leggi i top-N GA strategies dal Redis (l'ultimo run completato)
    2. Per ogni strategia: fetch ultime ~200 candele OHLCV (timeframe della strategia)
    3. Calcola signals (entries, exits) dalla strategy fn
    4. Per ogni segnale aperto/chiuso: crea o chiudi un PaperTrade
    5. Mark-to-market: calcola equity = balance + Σ holdings × current_price
    6. Snapshot in equity_snapshots

Idempotente:
    - PaperTrade ha (strategy_id, entry_time, symbol, side) come unique-ish:
      verifichiamo "open" prima di creare nuovo trade
    - EquitySnapshot ha PK (portfolio_id, timestamp): se chiamato 2 volte
      stesso minuto, secondo fallisce (acceptable, log warning)

Run via APScheduler (slice 4.0b registra job paper.engine_tick).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.strategies import get_strategy
from app.core.config import get_settings
from app.core.logging import get_logger
from app.ga import state as ga_state
from app.models.market import OHLCV
from app.models.paper import EquitySnapshot, PaperTrade
from app.repositories import ohlcv as ohlcv_repo

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PaperEngineConfig:
    """Configurazione del paper engine.

    top_n_strategies: quante delle migliori strategie del GA usare per
                     generare segnali (1 = solo la migliore).
    candles_lookback: quante candele caricare per calcolare i segnali
                     (deve essere ≥ max indicator lookback).
    min_sharpe_robust: soglia minima per considerare una strategia
                     "tradeabile" (filter di confidence gate).
    """

    portfolio_id: str = "paper-v1"
    top_n_strategies: int = 3
    candles_lookback: int = 300
    min_sharpe_robust: float = 0.5


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


async def run_engine_tick(
    session: AsyncSession,
    *,
    config: PaperEngineConfig | None = None,
) -> dict[str, Any]:
    """Esegue 1 tick del paper engine: signals → trades → equity snapshot.

    Returns:
        Dict con stats del tick: strategies_processed, trades_opened,
        trades_closed, equity_after, errors.
    """
    cfg = config or PaperEngineConfig()
    settings = get_settings()
    log.info("paper.engine.tick.start", portfolio_id=cfg.portfolio_id)

    # 1. Trova le top strategie dal GA (ultimo completed run)
    ga_runs = await ga_state.list_states(limit=20)
    completed = [r for r in ga_runs if r.status == "completed"]
    if not completed:
        log.warning("paper.engine.no_completed_ga_run")
        return {
            "status": "no_strategies",
            "reason": "no completed GA runs available",
            "strategies_processed": 0,
            "trades_opened": 0,
            "trades_closed": 0,
        }

    last_run = max(completed, key=lambda r: r.completed_at or 0)
    top_strategies = sorted(
        last_run.strategies,
        key=lambda s: s.sharpe_robust,
        reverse=True,
    )[: cfg.top_n_strategies]

    # Filtro confidence gate
    tradeable = [s for s in top_strategies if s.sharpe_robust >= cfg.min_sharpe_robust]
    if not tradeable:
        log.warning(
            "paper.engine.no_tradeable_strategies",
            top_sharpe=top_strategies[0].sharpe_robust if top_strategies else None,
        )
        return {
            "status": "no_tradeable",
            "reason": f"all top strategies below min_sharpe_robust={cfg.min_sharpe_robust}",
            "strategies_processed": 0,
            "trades_opened": 0,
            "trades_closed": 0,
        }

    symbol = last_run.config.symbol
    timeframe = last_run.config.timeframe
    strategy_id = last_run.config.strategy_id

    # 2. Fetch ultime N candele
    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=symbol,
        timeframe=timeframe,
        limit=cfg.candles_lookback,
        order="asc",
    )
    if len(rows) < 50:
        log.warning(
            "paper.engine.insufficient_candles",
            symbol=symbol,
            timeframe=timeframe,
            n=len(rows),
        )
        return {
            "status": "insufficient_data",
            "reason": f"only {len(rows)} candles available for {symbol} {timeframe}",
            "strategies_processed": 0,
            "trades_opened": 0,
            "trades_closed": 0,
        }

    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for r in rows
        ]
    ).set_index("timestamp")

    last_candle_ts = df.index[-1].to_pydatetime()
    last_close = float(df["close"].iloc[-1])

    spec = get_strategy(strategy_id)
    trades_opened = 0
    trades_closed = 0
    errors: list[str] = []

    # 3. Per ogni strategia tradeable: calcola signals correnti
    for rank, snap in enumerate(tradeable):
        try:
            params = snap.chromosome.copy()
            position_size_pct = float(params.pop("position_size_pct", 50.0))
            entries, exits = spec.fn(df, params)

            # Controlla l'ultima candela: c'è un entry o exit signal?
            last_entry = bool(entries.iloc[-1])
            last_exit = bool(exits.iloc[-1])

            # Cerca trade aperti per questa strategia (in mancanza di
            # strategy_id FK al PaperTrade, usiamo open_context come tag)
            strategy_tag = f"{strategy_id}_rank{rank}"
            open_q = await session.execute(
                select(PaperTrade)
                .where(
                    PaperTrade.symbol == symbol,
                    PaperTrade.timeframe == timeframe,
                    PaperTrade.status == "open",
                    PaperTrade.open_context["tag"].astext == strategy_tag,
                )
            )
            existing_open = open_q.scalar_one_or_none()

            # CHIUSURA: se c'è exit signal e abbiamo trade aperto
            if existing_open and last_exit:
                pnl = _close_trade(
                    existing_open,
                    exit_price=last_close,
                    exit_time=last_candle_ts,
                    fees_pct=float(settings.paper_fee_taker),
                    slippage_bps=float(settings.paper_slippage_bps),
                )
                trades_closed += 1
                log.info(
                    "paper.engine.trade.closed",
                    strategy_tag=strategy_tag,
                    entry=float(existing_open.entry_price),
                    exit=last_close,
                    pnl=float(pnl),
                )

            # APERTURA: se c'è entry signal e nessun trade aperto
            elif not existing_open and last_entry:
                # Calcola quantity in base al position_size_pct e al balance corrente
                balance = await _get_current_balance(session, cfg.portfolio_id, settings)
                size_quote = balance * (position_size_pct / 100.0)
                # Slippage sulla entry
                slippage = last_close * float(settings.paper_slippage_bps) / 10_000
                effective_entry_price = last_close + slippage
                quantity = size_quote / effective_entry_price
                fees = size_quote * float(settings.paper_fee_taker)

                trade = PaperTrade(
                    id=uuid.uuid4(),
                    strategy_id=None,  # FK opzionale (strategies tabella in future slice)
                    symbol=symbol,
                    timeframe=timeframe,
                    side="long",
                    status="open",
                    quantity=Decimal(str(quantity)),
                    entry_price=Decimal(str(effective_entry_price)),
                    entry_time=last_candle_ts,
                    fees=Decimal(str(fees)),
                    open_context={
                        "tag": strategy_tag,
                        "rank": rank,
                        "sharpe_robust": float(snap.sharpe_robust),
                        "chromosome": _native(snap.chromosome),
                    },
                )
                session.add(trade)
                trades_opened += 1
                log.info(
                    "paper.engine.trade.opened",
                    strategy_tag=strategy_tag,
                    entry=effective_entry_price,
                    qty=quantity,
                    size_quote=size_quote,
                )

        except Exception as exc:  # pragma: no cover
            errors.append(f"rank={rank}: {exc}")
            log.exception(
                "paper.engine.strategy.failed", rank=rank, error=str(exc)
            )

    # 4. Mark-to-market: calcola equity = balance + Σ open positions × close
    snapshot = await _build_equity_snapshot(
        session,
        portfolio_id=cfg.portfolio_id,
        last_close=last_close,
        symbol=symbol,
        snapshot_ts=datetime.now(timezone.utc),
        settings=settings,
    )
    session.add(snapshot)

    await session.flush()

    return {
        "status": "ok",
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy_id": strategy_id,
        "strategies_processed": len(tradeable),
        "trades_opened": trades_opened,
        "trades_closed": trades_closed,
        "equity_after": float(snapshot.equity),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _close_trade(
    trade: PaperTrade,
    *,
    exit_price: float,
    exit_time: datetime,
    fees_pct: float,
    slippage_bps: float,
) -> Decimal:
    """Chiudi trade in-place: setta exit_*, calcola pnl/pnl_pct/fees totali."""
    slippage = exit_price * slippage_bps / 10_000
    effective_exit = exit_price - slippage  # long → vendo, slippage negativo

    qty = float(trade.quantity)
    entry = float(trade.entry_price)
    exit_fees = qty * effective_exit * fees_pct

    pnl = qty * (effective_exit - entry) - exit_fees - float(trade.fees)
    pnl_pct = (effective_exit - entry) / entry if entry > 0 else 0.0

    trade.exit_price = Decimal(str(effective_exit))
    trade.exit_time = exit_time
    trade.fees = Decimal(str(float(trade.fees) + exit_fees))
    trade.pnl = Decimal(str(pnl))
    trade.pnl_pct = pnl_pct
    trade.status = "closed_signal"
    trade.close_context = {
        "exit_price": effective_exit,
        "exit_time": exit_time.isoformat(),
        "pnl": pnl,
    }
    return Decimal(str(pnl))


async def _get_current_balance(
    session: AsyncSession,
    portfolio_id: str,
    settings: Any,
) -> float:
    """Balance quote (USDT) corrente dal latest snapshot. Fallback al balance iniziale."""
    last_q = await session.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.portfolio_id == portfolio_id)
        .order_by(desc(EquitySnapshot.timestamp))
        .limit(1)
    )
    last = last_q.scalar_one_or_none()
    if last is None:
        return float(settings.paper_initial_balance_usdt)
    return float(last.balance_quote)


async def _build_equity_snapshot(
    session: AsyncSession,
    *,
    portfolio_id: str,
    last_close: float,
    symbol: str,
    snapshot_ts: datetime,
    settings: Any,
) -> EquitySnapshot:
    """Costruisce snapshot equity: balance + posizioni aperte mark-to-market."""
    # Balance corrente (dal precedente snapshot)
    last_q = await session.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.portfolio_id == portfolio_id)
        .order_by(desc(EquitySnapshot.timestamp))
        .limit(1)
    )
    last = last_q.scalar_one_or_none()
    initial = Decimal(str(settings.paper_initial_balance_usdt))

    if last is None:
        balance = initial
        peak_equity = initial
    else:
        # Aggiungi pnl dei trade chiusi DOPO l'ultimo snapshot
        new_closed_q = await session.execute(
            select(PaperTrade)
            .where(
                PaperTrade.status != "open",
                PaperTrade.exit_time > last.timestamp,
                PaperTrade.pnl.is_not(None),
            )
        )
        new_closed = list(new_closed_q.scalars().all())
        delta_pnl = sum((t.pnl for t in new_closed), Decimal("0"))
        balance = Decimal(str(last.balance_quote)) + delta_pnl
        peak_equity = Decimal(str(last.equity))

    # Apri posizioni: holdings dict + valore mark-to-market
    open_q = await session.execute(
        select(PaperTrade)
        .where(PaperTrade.status == "open")
    )
    open_trades = list(open_q.scalars().all())

    holdings: dict[str, dict[str, str]] = {}
    open_equity = Decimal("0")
    for t in open_trades:
        # Mark-to-market: usa last_close per il symbol corrente, entry_price altrimenti
        mark_price = last_close if t.symbol == symbol else float(t.entry_price)
        position_value = Decimal(str(float(t.quantity) * mark_price))
        # Riduco balance del costo di apertura (entry × qty)
        entry_cost = Decimal(str(float(t.entry_price) * float(t.quantity)))
        balance -= entry_cost
        open_equity += position_value
        existing = holdings.get(t.symbol, {"qty": "0", "avg_price": "0"})
        new_qty = float(existing["qty"]) + float(t.quantity)
        # Prezzo medio ponderato
        prev_total = float(existing["qty"]) * float(existing["avg_price"])
        new_total = prev_total + float(t.quantity) * float(t.entry_price)
        avg = new_total / new_qty if new_qty > 0 else float(t.entry_price)
        holdings[t.symbol] = {"qty": str(new_qty), "avg_price": str(avg)}

    equity = balance + open_equity
    if equity > peak_equity:
        peak_equity = equity
    drawdown = float((peak_equity - equity) / peak_equity) if peak_equity > 0 else 0.0

    return EquitySnapshot(
        timestamp=snapshot_ts,
        portfolio_id=portfolio_id,
        balance_quote=balance,
        holdings=holdings,
        equity=equity,
        drawdown_from_peak=max(0.0, drawdown),
        open_positions_count=len(open_trades),
    )


def _native(d: dict[str, Any]) -> dict[str, Any]:
    """Cast numpy/Decimal scalars → Python native (JSONB-safe)."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if hasattr(v, "item"):
            out[k] = v.item()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out
