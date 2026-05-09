"""APScheduler integrato in FastAPI lifespan.

Architettura:
    - AsyncIOScheduler avviato al boot, fermato a shutdown
    - Job registrati con id costante (es. "news.auto_refresh")
    - Trigger IntervalTrigger configurato dai DEFAULT_SETTINGS
    - Ogni job legge il flag ``enabled`` dal DB PRIMA di eseguire — così
      togglare il flag prende effetto al prossimo tick (no restart)
    - Persistenza job state: in-memory (sufficiente per single-instance VPS)

Tradeoff: leggiamo il setting ad ogni tick. Costo trascurabile (1 SELECT
puntuale su PK key) vs il vantaggio di toggle senza restart.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.db import session_scope
from app.core.logging import get_logger
from app.system import settings as settings_repo

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Tracking ultima esecuzione per ogni job — esposto via /api/v1/system/jobs
_last_runs: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def start_scheduler() -> None:
    """Avvia lo scheduler globale e registra i job dei settings 'automation'.

    Idempotente: se già avviato, no-op.
    """
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        executors={"default": AsyncIOExecutor()},
        timezone="UTC",
        job_defaults={
            "coalesce": True,  # se rimani indietro, non spawn N job duplicati
            "max_instances": 1,
            "misfire_grace_time": 30,
        },
    )

    _register_jobs(_scheduler)
    _scheduler.start()
    log.info("system.scheduler.started", jobs=[j.id for j in _scheduler.get_jobs()])


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("system.scheduler.stopped")


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def get_jobs_status() -> list[dict[str, Any]]:
    """Snapshot dei job per UI: id, next_run, last_run, last_status."""
    if _scheduler is None:
        return []
    out: list[dict[str, Any]] = []
    for job in _scheduler.get_jobs():
        last = _last_runs.get(job.id, {})
        out.append(
            {
                "id": job.id,
                "name": job.name or job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
                "last_run_at": last.get("at"),
                "last_status": last.get("status"),
                "last_message": last.get("message"),
                "last_duration_s": last.get("duration_s"),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Job registration
# ---------------------------------------------------------------------------


def _register_jobs(sched: AsyncIOScheduler) -> None:
    """Registra i job 'automation' con interval default. Il flag enabled
    viene riletto ad ogni tick — quindi il job può essere registrato ma no-op."""

    sched.add_job(
        _job_news_auto_refresh,
        trigger=IntervalTrigger(seconds=300),
        id="news.auto_refresh",
        name="News auto refresh (RSS fetch + ingest)",
        replace_existing=True,
    )
    sched.add_job(
        _job_news_auto_score,
        trigger=IntervalTrigger(seconds=600),
        id="news.auto_score",
        name="News auto score (Claude Haiku batch)",
        replace_existing=True,
    )
    sched.add_job(
        _job_ohlcv_auto_backfill,
        trigger=IntervalTrigger(seconds=3600),
        id="ohlcv.auto_backfill",
        name="OHLCV auto backfill (Binance)",
        replace_existing=True,
    )


# ---------------------------------------------------------------------------
# Run-record helper
# ---------------------------------------------------------------------------


def _record(job_id: str, status: str, message: str, duration_s: float) -> None:
    _last_runs[job_id] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "message": message,
        "duration_s": duration_s,
    }


def _now_ts() -> float:
    return asyncio.get_event_loop().time()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


async def _job_news_auto_refresh() -> None:
    job_id = "news.auto_refresh"
    started = _now_ts()
    try:
        async with session_scope() as session:
            cfg = await settings_repo.get_value(session, job_id)
            if not cfg.get("enabled"):
                _record(job_id, "skipped", "disabled", _now_ts() - started)
                return

            from app.news import fetch_and_ingest

            result = await fetch_and_ingest(session)
            _record(
                job_id,
                "ok",
                f"fetched={result['fetched']} inserted={result['inserted']}",
                _now_ts() - started,
            )
            log.info("system.scheduler.news_refresh.done", **result)
    except Exception as exc:
        _record(job_id, "error", str(exc), _now_ts() - started)
        log.exception("system.scheduler.news_refresh.failed", error=str(exc))


async def _job_news_auto_score() -> None:
    job_id = "news.auto_score"
    started = _now_ts()
    try:
        async with session_scope() as session:
            cfg = await settings_repo.get_value(session, job_id)
            if not cfg.get("enabled"):
                _record(job_id, "skipped", "disabled", _now_ts() - started)
                return

            from app.news import score_pending_news

            result = await score_pending_news(
                session,
                limit=int(cfg.get("batch_limit", 20)),
                concurrency=int(cfg.get("concurrency", 4)),
            )
            _record(
                job_id,
                "ok",
                f"picked={result['picked']} scored={result['scored']} failed={result['failed']}",
                _now_ts() - started,
            )
            log.info("system.scheduler.news_score.done", **result)
    except Exception as exc:
        _record(job_id, "error", str(exc), _now_ts() - started)
        log.exception("system.scheduler.news_score.failed", error=str(exc))


async def _job_ohlcv_auto_backfill() -> None:
    job_id = "ohlcv.auto_backfill"
    started = _now_ts()
    try:
        async with session_scope() as session:
            cfg = await settings_repo.get_value(session, job_id)
            if not cfg.get("enabled"):
                _record(job_id, "skipped", "disabled", _now_ts() - started)
                return

            # Backfill incrementale: ultime 48h per ogni symbol×timeframe.
            # ON CONFLICT DO NOTHING in upsert ohlcv → idempotente.
            from datetime import timedelta

            from app.core.config import get_settings as get_app_settings
            from app.exchanges.binance import BinanceConnector

            app_s = get_app_settings()
            window_start = datetime.now(timezone.utc) - timedelta(hours=48)

            total_inserted = 0
            async with BinanceConnector() as connector:
                for symbol in app_s.symbols:
                    for tf in app_s.timeframes:
                        n = await connector.backfill_ohlcv(
                            session=session,
                            symbol=symbol,
                            timeframe=tf,
                            start=window_start,
                        )
                        total_inserted += n

            _record(
                job_id,
                "ok",
                f"new_candles={total_inserted}",
                _now_ts() - started,
            )
            log.info("system.scheduler.ohlcv_backfill.done", n=total_inserted)
    except Exception as exc:
        _record(job_id, "error", str(exc), _now_ts() - started)
        log.exception("system.scheduler.ohlcv_backfill.failed", error=str(exc))


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------


JOB_FUNCS: dict[str, Any] = {
    "news.auto_refresh": _job_news_auto_refresh,
    "news.auto_score": _job_news_auto_score,
    "ohlcv.auto_backfill": _job_ohlcv_auto_backfill,
}


async def trigger_now(job_id: str) -> None:
    """Esegue immediatamente un job ignorando il flag enabled.

    Implementato come chiamata diretta della coroutine — bypassa lo
    scheduler così possiamo restituire un risultato sincrono.
    """
    fn = JOB_FUNCS.get(job_id)
    if fn is None:
        raise KeyError(f"Job '{job_id}' non registrato")
    # Forziamo enabled=true temporaneamente lavorando direttamente sulla logica:
    # più semplice clonare la logica, ma riusiamo via setting temporaneo.
    # Nota: usiamo un override in-memory invece che toccare DB
    await _force_run(job_id, fn)


async def _force_run(job_id: str, fn: Any) -> None:
    """Wrapper che esegue la coroutine bypassando il check enabled.

    Trick: settiamo un flag temporaneo che il job legge.
    """
    started = _now_ts()
    try:
        async with session_scope() as session:
            cfg = await settings_repo.get_value(session, job_id)
            # Override locale: facciamo upsert temporaneo di enabled=true,
            # eseguiamo, ripristiniamo. Questo MODIFICA il DB per mezzo
            # secondo — accettabile per un trigger admin manuale.
            #
            # Alternativa più pulita: refactoring dei job in _do_work() vs
            # _job_xxx wrapper. La faremo in un seguente commit se
            # necessario.
            original_enabled = cfg.get("enabled", False)
            if not original_enabled:
                cfg["enabled"] = True
                await settings_repo.set_setting_value(session, job_id, cfg)
                await session.commit()

        # Adesso il job vede enabled=true e procede
        await fn()

        if not original_enabled:
            async with session_scope() as session:
                cfg["enabled"] = False
                await settings_repo.set_setting_value(session, job_id, cfg)
                await session.commit()
    except Exception as exc:
        _record(job_id, "error", str(exc), _now_ts() - started)
        log.exception("system.scheduler.manual_trigger.failed", job=job_id)
        raise
