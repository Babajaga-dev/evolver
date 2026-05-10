"""Repository CRUD per replay_runs / events / snapshots."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.replay import ReplayEquitySnapshot, ReplayRetrainEvent, ReplayRun


async def create_run(
    session: AsyncSession,
    *,
    name: str,
    symbol: str,
    config: dict[str, Any],
) -> ReplayRun:
    run = ReplayRun(
        id=uuid.uuid4(),
        name=name,
        status="pending",
        symbol=symbol,
        config=config,
        current_equity=float(config.get("initial_cash", 10000.0)),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> ReplayRun | None:
    res = await session.execute(select(ReplayRun).where(ReplayRun.id == run_id))
    return res.scalars().first()


async def list_runs(session: AsyncSession, limit: int = 50) -> list[ReplayRun]:
    res = await session.execute(
        select(ReplayRun).order_by(desc(ReplayRun.created_at)).limit(limit)
    )
    return list(res.scalars().all())


async def update_status(
    session: AsyncSession,
    run_id: uuid.UUID,
    status: str,
    *,
    error: str | None = None,
) -> None:
    await session.execute(
        update(ReplayRun)
        .where(ReplayRun.id == run_id)
        .values(status=status, error=error, last_heartbeat=datetime.now(timezone.utc))
    )
    await session.commit()


async def update_progress(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    current_simulated_date: datetime,
    current_equity: float,
    progress_pct: float,
) -> None:
    await session.execute(
        update(ReplayRun)
        .where(ReplayRun.id == run_id)
        .values(
            current_simulated_date=current_simulated_date,
            current_equity=current_equity,
            progress_pct=progress_pct,
            last_heartbeat=datetime.now(timezone.utc),
        )
    )
    await session.commit()


async def append_retrain_event(
    session: AsyncSession,
    *,
    replay_id: uuid.UUID,
    t: datetime,
    trigger: str,
    organism: dict[str, Any],
    elapsed_seconds: float,
    equity_at_retrain: float,
) -> None:
    ev = ReplayRetrainEvent(
        replay_id=replay_id,
        t=t,
        trigger=trigger,
        organism=organism,
        elapsed_seconds=elapsed_seconds,
        equity_at_retrain=equity_at_retrain,
    )
    session.add(ev)
    # n_retrains++
    await session.execute(
        update(ReplayRun)
        .where(ReplayRun.id == replay_id)
        .values(n_retrains=ReplayRun.n_retrains + 1)
    )
    if trigger == "kill_switch":
        await session.execute(
            update(ReplayRun)
            .where(ReplayRun.id == replay_id)
            .values(n_kill_switch_events=ReplayRun.n_kill_switch_events + 1)
        )
    await session.commit()


async def append_equity_batch(
    session: AsyncSession,
    *,
    replay_id: uuid.UUID,
    rows: list[dict[str, Any]],
) -> None:
    if not rows:
        return
    objs = [ReplayEquitySnapshot(replay_id=replay_id, **r) for r in rows]
    session.add_all(objs)
    await session.commit()


async def set_final_metrics(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    final_metrics: dict[str, Any],
) -> None:
    await session.execute(
        update(ReplayRun)
        .where(ReplayRun.id == run_id)
        .values(
            final_metrics=final_metrics,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            progress_pct=100.0,
        )
    )
    await session.commit()


async def delete_run(session: AsyncSession, run_id: uuid.UUID) -> bool:
    """Cancella run + cascade su retrain_events + equity_snapshots."""
    res = await session.execute(delete(ReplayRun).where(ReplayRun.id == run_id))
    await session.commit()
    return res.rowcount > 0


async def delete_all(session: AsyncSession) -> int:
    """Wipe completo della tabella replay_runs (cascade su events + snapshots)."""
    res = await session.execute(delete(ReplayRun))
    await session.commit()
    return res.rowcount or 0


async def get_retrain_events(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> list[ReplayRetrainEvent]:
    res = await session.execute(
        select(ReplayRetrainEvent)
        .where(ReplayRetrainEvent.replay_id == run_id)
        .order_by(ReplayRetrainEvent.t)
    )
    return list(res.scalars().all())


async def get_equity_snapshots(
    session: AsyncSession,
    run_id: uuid.UUID,
    *,
    limit: int = 5000,
) -> list[ReplayEquitySnapshot]:
    res = await session.execute(
        select(ReplayEquitySnapshot)
        .where(ReplayEquitySnapshot.replay_id == run_id)
        .order_by(ReplayEquitySnapshot.t)
        .limit(limit)
    )
    return list(res.scalars().all())
