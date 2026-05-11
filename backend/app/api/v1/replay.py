"""Endpoint /api/v1/replay/*"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.replay import repo as replay_repo
from app.replay.runner import run_replay_task
from app.schemas.replay import (
    ReplayDetailResponse,
    ReplayEquityPointOut,
    ReplayListResponse,
    ReplayRetrainEventOut,
    ReplayRunSummary,
    ReplayStartRequest,
)

router = APIRouter(tags=["replay"], prefix="/replay")
log = get_logger(__name__)


def _to_summary(r) -> ReplayRunSummary:
    return ReplayRunSummary(
        id=r.id,
        name=r.name,
        status=r.status,
        symbol=r.symbol,
        current_simulated_date=r.current_simulated_date,
        current_equity=r.current_equity,
        progress_pct=r.progress_pct,
        n_retrains=r.n_retrains,
        n_kill_switch_events=r.n_kill_switch_events,
        started_at=r.started_at,
        completed_at=r.completed_at,
        error=r.error,
        created_at=r.created_at,
        final_metrics=r.final_metrics,
        config=r.config,
    )


@router.post("/runs", response_model=ReplayRunSummary)
async def start_replay(
    body: ReplayStartRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ReplayRunSummary:
    if body.end_date <= body.start_date:
        raise HTTPException(400, "end_date deve essere > start_date")
    cfg = body.model_dump(mode="json")
    run = await replay_repo.create_run(
        session, name=body.name, symbol=body.symbol, config=cfg
    )
    # Lancia in background
    asyncio.create_task(run_replay_task(run.id))
    log.info("replay.api.start", run_id=str(run.id))
    return _to_summary(run)


@router.get("/runs", response_model=ReplayListResponse)
async def list_replays(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=200),
) -> ReplayListResponse:
    try:
        runs = await replay_repo.list_runs(session, limit=limit)
        return ReplayListResponse(runs=[_to_summary(r) for r in runs])
    except Exception as exc:
        log.exception("replay.list_failed", error=str(exc))
        raise HTTPException(500, f"replay list failed: {type(exc).__name__}: {exc}")


@router.get("/runs/{run_id}", response_model=ReplayDetailResponse)
async def get_replay(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    snapshot_limit: int = Query(default=5000, ge=10, le=50_000),
) -> ReplayDetailResponse:
    run = await replay_repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(404, "replay run not found")
    snaps = await replay_repo.get_equity_snapshots(session, run_id, limit=snapshot_limit)
    events = await replay_repo.get_retrain_events(session, run_id)
    return ReplayDetailResponse(
        summary=_to_summary(run),
        equity_curve=[
            ReplayEquityPointOut(
                t=s.t,
                equity=s.equity,
                position_size_pct=s.position_size_pct,
                drawdown_pct=s.drawdown_pct,
                regime=s.regime,
                n_trades_so_far=s.n_trades_so_far,
            )
            for s in snaps
        ],
        retrain_events=[
            ReplayRetrainEventOut(
                t=e.t,
                trigger=e.trigger,
                organism=e.organism,
                elapsed_seconds=e.elapsed_seconds,
                equity_at_retrain=e.equity_at_retrain,
            )
            for e in events
        ],
    )


@router.post("/runs/{run_id}/stop")
async def stop_replay(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    run = await replay_repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(404, "replay run not found")
    if run.status not in ("running", "pending"):
        return {"ok": False, "message": f"run is {run.status}, nothing to stop"}
    await replay_repo.update_status(session, run_id, "stopping")
    return {"ok": True, "message": "stop requested; the loop will exit gracefully"}


@router.delete("/runs/{run_id}")
async def delete_replay(
    run_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    ok = await replay_repo.delete_run(session, run_id)
    if not ok:
        raise HTTPException(404, "replay run not found")
    return {"ok": True}


@router.delete("/runs")
async def delete_all_replays(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    confirm: str = Query(...),
) -> dict:
    if confirm != "yes":
        raise HTTPException(400, "confirm=yes richiesto")
    n = await replay_repo.delete_all(session)
    return {"ok": True, "deleted": n}


# ---------------------------------------------------------------------------
# Admin: historical backfill one-shot
# ---------------------------------------------------------------------------
from app.schemas.replay import AdminBackfillRequest, AdminBackfillResponse


async def _backfill_job(req: AdminBackfillRequest) -> None:
    from app.core.db import session_scope
    from app.exchanges.binance import BinanceConnector

    end = req.end_date or datetime.now(timezone.utc)
    log.info("admin.backfill.start", symbols=req.symbols, tfs=req.timeframes,
             start=req.start_date.isoformat(), end=end.isoformat())
    async with BinanceConnector() as conn:
        # 1. OHLCV
        for sym in req.symbols:
            for tf in req.timeframes:
                try:
                    async with session_scope() as s:
                        n = await conn.backfill_ohlcv(
                            session=s, symbol=sym, timeframe=tf,
                            start=req.start_date, end=end,
                        )
                    log.info("admin.backfill.ohlcv.done", symbol=sym, tf=tf, inserted=n)
                except Exception as exc:
                    log.exception("admin.backfill.ohlcv.failed", symbol=sym, tf=tf, error=str(exc))
        # 2. Funding rates (perpetual)
        for sym in req.symbols:
            try:
                async with session_scope() as s:
                    n = await conn.backfill_funding_rates(
                        session=s, symbol=sym, start=req.start_date, end=end,
                    )
                log.info("admin.backfill.funding.done", symbol=sym, inserted=n)
            except Exception as exc:
                log.exception("admin.backfill.funding.failed", symbol=sym, error=str(exc))
    log.info("admin.backfill.complete")


@router.post("/admin/backfill", response_model=AdminBackfillResponse)
async def admin_backfill(body: AdminBackfillRequest) -> AdminBackfillResponse:
    asyncio.create_task(_backfill_job(body))
    return AdminBackfillResponse(
        started=True,
        job_id=str(uuid.uuid4()),
        message=f"Backfill avviato in background per {len(body.symbols)}×{len(body.timeframes)} = {len(body.symbols)*len(body.timeframes)} stream",
    )
