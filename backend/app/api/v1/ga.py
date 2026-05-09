"""Endpoint GA — start run + polling status.

In-memory state management per Slice 2.0a (DB persistence in slice
successivo). Stato perso al restart del backend; OK per dimostrazione
browser-provable.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.strategies import get_strategy
from app.core.config import get_settings
from app.core.db import get_db_session, session_scope
from app.core.logging import get_logger
from app.ga import state as state_store
from app.ga.runner import GaConfig, GaRunner, RunState
from app.models.market import ALLOWED_TIMEFRAMES
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.ga import (
    GaRunCreated,
    GaRunRequest,
    GaRunStatus,
    GaRunSummary,
    GaRunsListResponse,
    GenerationSnapshotOut,
    StrategySnapshotOut,
)

router = APIRouter(tags=["ga"])
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/ga/runs",
    response_model=GaRunCreated,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_ga_run(
    req: GaRunRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GaRunCreated:
    """Avvia un nuovo GA run in background. Ritorna immediatamente con un
    population_id. Il run procede in un task asyncio; usa
    GET /api/v1/ga/runs/{id} per pollare il progresso.
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

    # Fetch OHLCV (validato + caricato qui per fail-fast prima del task)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=req.period_days)
    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=req.symbol,
        timeframe=req.timeframe,
        start=start,
        end=end,
        limit=20_000,
        order="asc",
    )
    min_required = 50 * req.n_windows
    if len(rows) < min_required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Dati insufficienti: {len(rows)} candele. "
                f"Servono almeno {min_required} per {req.n_windows} finestre."
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

    population_id = str(uuid.uuid4())[:8]  # short id leggibile
    config = GaConfig(
        strategy_id=req.strategy_id,
        symbol=req.symbol,
        timeframe=req.timeframe,
        period_days=req.period_days,
        initial_cash=req.initial_cash,
        population_size=req.population_size,
        n_generations=req.n_generations,
        n_windows=req.n_windows,
        seed=req.seed,
        fee=settings.paper_fee_taker,
        slippage_bps=settings.paper_slippage_bps,
    )
    state = RunState(population_id=population_id, config=config)

    # Persist initial state su Redis (frontend può subito iniziare a pollare)
    await state_store.save_state(state)

    log.info(
        "ga.run.scheduled",
        population_id=population_id,
        strategy=req.strategy_id,
        pop_size=req.population_size,
        n_gen=req.n_generations,
        n_candles=len(df),
    )

    # Background task
    async def _runner() -> None:
        runner = GaRunner(config=config, df=df)
        try:
            await runner.run_async(state)
            log.info(
                "ga.run.completed",
                population_id=population_id,
                generations=len(state.generations),
                strategies=len(state.strategies),
            )
        except Exception as exc:
            log.exception("ga.run.error", population_id=population_id, error=str(exc))
            state.status = "failed"
            state.error = str(exc)
            try:
                await state_store.save_state(state)
            except Exception:  # pragma: no cover
                pass

    asyncio.create_task(_runner())

    return GaRunCreated(population_id=population_id, status="pending")


@router.get("/ga/runs", response_model=GaRunsListResponse)
async def list_ga_runs() -> GaRunsListResponse:
    """Lista riassunto di tutti i runs in Redis."""
    states = await state_store.list_states(limit=50)
    summaries: list[GaRunSummary] = []
    for state in states:
        best = (
            max(state.strategies, key=lambda s: s.sharpe_robust).sharpe_robust
            if state.strategies
            else None
        )
        summaries.append(
            GaRunSummary(
                population_id=state.population_id,
                strategy_id=state.config.strategy_id,
                symbol=state.config.symbol,
                timeframe=state.config.timeframe,
                status=state.status,
                current_generation=state.current_generation,
                total_generations=state.config.n_generations,
                started_at=(
                    datetime.fromtimestamp(state.started_at, tz=timezone.utc)
                    if state.started_at
                    else None
                ),
                best_sharpe_robust=best,
            )
        )
    summaries.sort(
        key=lambda s: (s.started_at or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )
    return GaRunsListResponse(runs=summaries)


@router.get("/ga/runs/{population_id}", response_model=GaRunStatus)
async def get_ga_run_status(population_id: str) -> GaRunStatus:
    """Snapshot completo del run — usato dal frontend per polling."""
    state = await state_store.get_state(population_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{population_id}' non trovato",
        )

    pareto = _extract_pareto_front(state)
    top = _extract_top_strategies(state, n=10)

    elapsed = 0.0
    if state.started_at:
        end_t = state.completed_at or asyncio.get_event_loop().time()
        # state.started_at è time.time(); ricalcolare con time.time()
        import time

        end_real = state.completed_at or time.time()
        elapsed = end_real - state.started_at

    return GaRunStatus(
        population_id=state.population_id,
        strategy_id=state.config.strategy_id,
        symbol=state.config.symbol,
        timeframe=state.config.timeframe,
        status=state.status,
        current_generation=state.current_generation,
        total_generations=state.config.n_generations,
        population_size=state.config.population_size,
        started_at=(
            datetime.fromtimestamp(state.started_at, tz=timezone.utc)
            if state.started_at
            else None
        ),
        completed_at=(
            datetime.fromtimestamp(state.completed_at, tz=timezone.utc)
            if state.completed_at
            else None
        ),
        elapsed_seconds=elapsed,
        error=state.error,
        generations=[
            GenerationSnapshotOut(
                generation=g.generation,
                best_fitness=g.best_fitness,
                mean_fitness=g.mean_fitness,
                worst_fitness=g.worst_fitness,
                std_fitness=g.std_fitness,
                best_sharpe_robust=g.best_sharpe_robust,
                best_max_dd=g.best_max_dd,
                diversity=g.diversity,
                elapsed_seconds=g.elapsed_seconds,
            )
            for g in state.generations
        ],
        pareto_front=[_to_strategy_out(s) for s in pareto],
        top_strategies=[_to_strategy_out(s) for s in top],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_strategy_out(s: Any) -> StrategySnapshotOut:
    return StrategySnapshotOut(
        chromosome=s.chromosome,
        sharpe_robust=s.sharpe_robust,
        max_drawdown_abs=s.max_drawdown_abs,
        complexity=s.complexity,
        n_trades=s.n_trades,
        n_windows_winning=s.n_windows_winning,
        generation=s.generation,
    )


def _extract_pareto_front(state: RunState) -> list:
    """Pareto front 2D su (sharpe_robust, max_drawdown_abs) — non dominati."""
    if not state.strategies:
        return []
    # Non-dominated set: (sharpe_max, mdd_min)
    candidates = list(state.strategies)
    pareto = []
    for s in candidates:
        dominated = False
        for other in candidates:
            if other is s:
                continue
            if (
                other.sharpe_robust >= s.sharpe_robust
                and other.max_drawdown_abs <= s.max_drawdown_abs
                and (
                    other.sharpe_robust > s.sharpe_robust
                    or other.max_drawdown_abs < s.max_drawdown_abs
                )
            ):
                dominated = True
                break
        if not dominated:
            pareto.append(s)
    pareto.sort(key=lambda x: x.max_drawdown_abs)
    return pareto[:50]  # cap a 50 per non gonfiare la response


def _extract_top_strategies(state: RunState, n: int = 10) -> list:
    """Top-N per Sharpe robusto."""
    if not state.strategies:
        return []
    return sorted(
        state.strategies,
        key=lambda s: s.sharpe_robust,
        reverse=True,
    )[:n]
