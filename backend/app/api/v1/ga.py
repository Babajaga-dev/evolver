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
    # train_end_days_ago: 0 = ora; >0 = train termina N giorni fa per
    # lasciare spazio a OOS validation sui dati successivi
    end = datetime.now(timezone.utc) - timedelta(days=int(getattr(req, 'train_end_days_ago', 0) or 0))
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
        train_end_at=end,
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
            float(max(state.strategies, key=lambda s: s.sharpe_robust).sharpe_robust)
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
                current_generation=int(state.current_generation),
                total_generations=int(state.config.n_generations),
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


@router.post("/ga/runs/{population_id}/stop")
async def stop_ga_run(population_id: str) -> dict:
    """Richiesta di stop graceful: il GA terminerà alla fine della
    generazione in corso (può richiedere fino a ~1 generazione di tempo).
    """
    state = await state_store.get_state(population_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{population_id}' non trovato",
        )
    if state.status not in {"pending", "running"}:
        return {
            "population_id": population_id,
            "status": state.status,
            "message": f"Run è già in stato '{state.status}', stop non applicabile",
        }
    state.should_stop = True
    await state_store.save_state(state)
    log.info("ga.run.stop_requested", population_id=population_id)
    return {
        "population_id": population_id,
        "status": "stopping",
        "message": "Stop richiesto. Il run terminerà alla fine della generazione corrente.",
    }


@router.delete("/ga/runs/{population_id}")
async def delete_ga_run(population_id: str) -> dict:
    """Cancella un run dalla persistence (Redis). Utile per cleanup di run
    falliti / vecchi.
    """
    deleted = await state_store.delete_state(population_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{population_id}' non trovato",
        )
    log.info("ga.run.deleted", population_id=population_id)
    return {"population_id": population_id, "deleted": True}


@router.delete("/ga/runs")
async def cleanup_ga_runs(
    status_filter: str | None = None,
) -> dict:
    """Bulk cleanup. ``status_filter='failed'`` cancella solo i run falliti.
    Senza filter, cancella *tutti* i run (uso amministrativo).
    """
    states = await state_store.list_states(limit=200)
    deleted_ids: list[str] = []
    for s in states:
        if status_filter is not None and s.status != status_filter:
            continue
        # Non cancelliamo run in esecuzione (rischio di disallinearsi)
        if s.status in {"pending", "running"}:
            continue
        ok = await state_store.delete_state(s.population_id)
        if ok:
            deleted_ids.append(s.population_id)
    log.info("ga.runs.bulk_deleted", n=len(deleted_ids), filter=status_filter)
    return {"deleted": len(deleted_ids), "ids": deleted_ids}


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
                generation=int(g.generation),
                best_fitness=float(g.best_fitness),
                mean_fitness=float(g.mean_fitness),
                worst_fitness=float(g.worst_fitness),
                std_fitness=float(g.std_fitness),
                best_sharpe_robust=float(g.best_sharpe_robust),
                best_max_dd=float(g.best_max_dd),
                diversity=float(g.diversity),
                elapsed_seconds=float(g.elapsed_seconds),
            )
            for g in state.generations
        ],
        pareto_front=[_to_strategy_out(s) for s in pareto],
        top_strategies=[_to_strategy_out(s) for s in top],
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_native(value: Any) -> Any:
    """Cast numpy/pandas scalars → Python native (Pydantic-safe).

    Difensivo: anche se runner.py fa già il cast a save time, gli state
    pre-fix sono in Redis con numpy types ancora dentro, quindi facciamo
    un secondo cast in lettura.
    """
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _native_dict(d: dict[str, Any]) -> dict[str, Any]:
    return {k: _to_native(v) for k, v in d.items()}


def _to_strategy_out(s: Any) -> StrategySnapshotOut:
    return StrategySnapshotOut(
        chromosome=_native_dict(s.chromosome),
        sharpe_robust=float(s.sharpe_robust),
        max_drawdown_abs=float(s.max_drawdown_abs),
        complexity=float(s.complexity),
        n_trades=int(s.n_trades),
        n_windows_winning=int(s.n_windows_winning),
        generation=int(s.generation),
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
