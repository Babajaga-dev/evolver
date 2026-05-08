"""Endpoint backtest engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest import (
    BacktestEngine,
    available_strategies,
    get_strategy,
)
from app.core.config import get_settings
from app.core.db import get_db_session
from app.core.logging import get_logger
from app.models.market import ALLOWED_TIMEFRAMES
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.backtest import (
    BacktestRequest,
    BacktestResponse,
    EquityPointOut,
    MetricsOut,
    StrategiesRegistryResponse,
    StrategyInfo,
    StrategyParamInfo,
    TradeRecordOut,
)

router = APIRouter(tags=["backtest"])
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Strategies registry
# ---------------------------------------------------------------------------


@router.get("/strategies", response_model=StrategiesRegistryResponse)
async def list_strategies() -> StrategiesRegistryResponse:
    """Tutte le strategie preset disponibili per backtest e GA (Fase 2)."""
    return StrategiesRegistryResponse(
        strategies=[
            StrategyInfo(
                id=spec.id,
                label=spec.label,
                family=spec.family,
                description=spec.description,
                params=[
                    StrategyParamInfo(
                        name=p.name,
                        type=p.type,
                        default=p.default,
                        min=p.min,
                        max=p.max,
                        description=p.description,
                    )
                    for p in spec.params
                ],
            )
            for spec in available_strategies()
        ]
    )


# ---------------------------------------------------------------------------
# Backtest run
# ---------------------------------------------------------------------------


@router.post("/backtest/run", response_model=BacktestResponse)
async def run_backtest(
    req: BacktestRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BacktestResponse:
    """Esegue un backtest single-strategy single-asset.

    Pipeline:
        1. Validate symbol/timeframe/strategy_id
        2. Fetch OHLCV dal DB per il period richiesto
        3. Esegue ``BacktestEngine.run()`` (vectorbt sotto)
        4. Serializza risultato → JSON
    """
    settings = get_settings()
    if req.symbol not in settings.symbols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{req.symbol}' non in universe attivo",
        )
    if req.timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{req.timeframe}' non supportato",
        )
    try:
        get_strategy(req.strategy_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=req.period_days)

    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=req.symbol,
        timeframe=req.timeframe,
        start=start,
        end=end,
        limit=10_000,
        order="asc",
    )
    if len(rows) < 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dati insufficienti: {len(rows)} candele nel range. "
                f"Servono almeno 50."
            ),
        )

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

    log.info(
        "backtest.start",
        symbol=req.symbol,
        timeframe=req.timeframe,
        strategy=req.strategy_id,
        n_candles=len(df),
    )

    try:
        engine = BacktestEngine(
            fee=settings.paper_fee_taker,
            slippage_bps=settings.paper_slippage_bps,
        )
        result = engine.run(
            df=df,
            strategy_id=req.strategy_id,
            params=req.params,
            symbol=req.symbol,
            timeframe=req.timeframe,
            initial_cash=req.initial_cash,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except Exception as exc:  # pragma: no cover
        log.exception("backtest.failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest engine error: {exc}",
        ) from exc

    log.info(
        "backtest.done",
        symbol=req.symbol,
        strategy=req.strategy_id,
        n_trades=result.metrics.n_trades,
        total_return=result.metrics.total_return,
        sharpe=result.metrics.sharpe,
    )

    return BacktestResponse(
        symbol=result.symbol,
        timeframe=result.timeframe,
        strategy_id=result.strategy_id,
        strategy_label=result.strategy_label,
        params=result.params,
        initial_cash=result.initial_cash,
        fee=result.fee,
        slippage=result.slippage,
        start=result.start,
        end=result.end,
        equity_curve=[
            EquityPointOut(
                timestamp=p.timestamp, equity=p.equity, drawdown=p.drawdown
            )
            for p in result.equity_curve
        ],
        trades=[
            TradeRecordOut(
                entry_time=t.entry_time,
                exit_time=t.exit_time,
                entry_price=t.entry_price,
                exit_price=t.exit_price,
                size=t.size,
                direction=t.direction,
                pnl=t.pnl,
                pnl_pct=t.pnl_pct,
            )
            for t in result.trades
        ],
        metrics=MetricsOut(**result.metrics.to_dict()),
    )
