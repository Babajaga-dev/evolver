"""OOS runner — orchestra train/test validation di un GA completato."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtest.engine import BacktestEngine
from app.core.logging import get_logger
from app.ga import state as ga_state
from app.repositories import ohlcv as ohlcv_repo

log = get_logger(__name__)


# Soglie verdict per singola strategia
DEGRADATION_ROBUST = 0.5  # sharpe_test/sharpe_train >= 0.5 → robust
SHARPE_MIN_TEST = 0.0  # sharpe test deve essere positivo


@dataclass
class OosEvolutionPoint:
    """Per ogni generazione del GA: best strategy in-sample + suo Sharpe OOS."""

    generation: int
    # In-sample (dal GA snapshot)
    best_sharpe_robust_train: float
    mean_sharpe_robust_train: float
    diversity: float
    # Out-of-sample (backtest del best chromosome di quella gen)
    best_sharpe_test: float | None
    best_total_return_test: float
    best_n_trades_test: int


@dataclass
class OosStrategyResult:
    """Risultato OOS per una singola strategia del Pareto."""

    rank: int
    chromosome: dict[str, Any]
    # Train metrics (da GA)
    sharpe_train: float
    max_drawdown_train: float
    n_trades_train: int
    # Test metrics (da backtest OOS)
    sharpe_test: float | None
    total_return_test: float
    max_drawdown_test: float
    n_trades_test: int
    win_rate_test: float | None
    final_equity_test: float
    # Verdict
    degradation_pct: float | None  # (sharpe_test - sharpe_train) / sharpe_train * 100
    verdict: str  # "robust" | "mixed" | "overfit" | "no_signal"
    verdict_reason: str


@dataclass
class OosResult:
    """Risultato aggregato dell'OOS validation."""

    population_id: str
    strategy_id: str
    symbol: str
    timeframe: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    test_days: int
    top_k: int
    initial_cash: float
    strategies: list[OosStrategyResult] = field(default_factory=list)
    evolution_curve: list[OosEvolutionPoint] = field(default_factory=list)
    overall_verdict: str = "unknown"  # "robust" | "mixed" | "overfit"
    overall_reason: str = ""
    n_robust: int = 0
    n_mixed: int = 0
    n_overfit: int = 0
    n_no_signal: int = 0


class OosError(Exception):
    """Sollevato quando OOS validation fallisce."""


async def validate_oos(
    session: AsyncSession,
    *,
    population_id: str,
    test_days: int = 90,
    top_k: int = 10,
    initial_cash: float = 10_000.0,
    fee: float = 0.001,
    slippage_bps: float = 2.0,
) -> OosResult:
    """Valida un GA completato su periodo test successivo al train.

    Args:
        population_id: ID del GA run (deve essere status=completed)
        test_days: lunghezza periodo OOS dopo train_end
        top_k: quante delle top strategie validare (per Sharpe)
        initial_cash, fee, slippage_bps: config backtest test
    """
    # 1. Recupera state GA
    state = await ga_state.get_state(population_id)
    if state is None:
        raise OosError(f"GA run '{population_id}' non trovato in Redis")
    if state.status != "completed":
        raise OosError(
            f"GA run '{population_id}' status={state.status} (deve essere 'completed')"
        )

    cfg = state.config
    if not state.strategies:
        raise OosError(f"GA run '{population_id}' non ha strategie evolute")

    # 2. Calcola periodo test (subito DOPO train_end)
    end_train = datetime.now(timezone.utc)
    if state.completed_at:
        end_train = datetime.fromtimestamp(state.completed_at, tz=timezone.utc)
    start_train = end_train - timedelta(days=cfg.period_days)

    start_test = end_train
    end_test = start_test + timedelta(days=test_days)
    # Cap a now: non possiamo testare nel futuro
    now = datetime.now(timezone.utc)
    if end_test > now:
        end_test = now
        actual_test_days = (end_test - start_test).days
    else:
        actual_test_days = test_days

    if actual_test_days < 7:
        raise OosError(
            f"Periodo test troppo corto ({actual_test_days}d). "
            f"Il GA è stato completato troppo recentemente — aspetta più dati."
        )

    # 3. Fetch candele test period
    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        start=start_test,
        end=end_test,
        limit=20_000,
        order="asc",
    )
    if len(rows) < 30:
        raise OosError(
            f"Dati test insufficienti: {len(rows)} candele in periodo "
            f"{start_test.isoformat()} -> {end_test.isoformat()}"
        )

    test_df = pd.DataFrame(
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

    # 4. Top K strategie ordinate per sharpe_robust
    top_strategies = sorted(
        state.strategies, key=lambda s: s.sharpe_robust, reverse=True
    )[:top_k]

    # 4b. Per OGNI generazione: prendi best chromosome di quella gen,
    # backtest OOS. Servirà per il chart "GA evolution vs OOS performance"
    engine = BacktestEngine(fee=fee, slippage_bps=slippage_bps)
    evolution_curve: list[OosEvolutionPoint] = []

    # Raggruppa strategie per generation, prendi best (Sharpe) per ognuna
    by_gen: dict[int, list[Any]] = {}
    for s in state.strategies:
        by_gen.setdefault(int(s.generation), []).append(s)

    for gen_snapshot in state.generations:
        gen = int(gen_snapshot.generation)
        candidates = by_gen.get(gen, [])
        if not candidates:
            evolution_curve.append(
                OosEvolutionPoint(
                    generation=gen,
                    best_sharpe_robust_train=float(gen_snapshot.best_sharpe_robust),
                    mean_sharpe_robust_train=-float(gen_snapshot.mean_fitness),
                    diversity=float(gen_snapshot.diversity),
                    best_sharpe_test=None,
                    best_total_return_test=0.0,
                    best_n_trades_test=0,
                )
            )
            continue

        # Best per quella generazione
        best = max(candidates, key=lambda s: s.sharpe_robust)
        chrom = dict(best.chromosome)
        psize = float(chrom.pop("position_size_pct", 100.0))

        try:
            res = engine.run(
                df=test_df,
                strategy_id=cfg.strategy_id,
                params=chrom,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                initial_cash=initial_cash,
                position_size_pct=psize,
            )
            sh_test = res.metrics.sharpe
            tr_test = float(res.metrics.total_return)
            nt_test = int(res.metrics.n_trades)
        except Exception as exc:
            log.warning("oos.evolution.backtest_failed", gen=gen, error=str(exc))
            sh_test = None
            tr_test = 0.0
            nt_test = 0

        evolution_curve.append(
            OosEvolutionPoint(
                generation=gen,
                best_sharpe_robust_train=float(best.sharpe_robust),
                mean_sharpe_robust_train=-float(gen_snapshot.mean_fitness),
                diversity=float(gen_snapshot.diversity),
                best_sharpe_test=sh_test,
                best_total_return_test=tr_test,
                best_n_trades_test=nt_test,
            )
        )

    # 5. Per ogni strategia: backtest su test period
    strategy_results: list[OosStrategyResult] = []

    for rank, snap in enumerate(top_strategies, start=1):
        chromosome = dict(snap.chromosome)
        position_size_pct = float(chromosome.pop("position_size_pct", 100.0))

        try:
            result = engine.run(
                df=test_df,
                strategy_id=cfg.strategy_id,
                params=chromosome,
                symbol=cfg.symbol,
                timeframe=cfg.timeframe,
                initial_cash=initial_cash,
                position_size_pct=position_size_pct,
            )
            metrics = result.metrics
            sharpe_test = metrics.sharpe
            total_return_test = float(metrics.total_return)
            max_dd_test = float(metrics.max_drawdown)
            n_trades_test = int(metrics.n_trades)
            win_rate_test = (
                float(metrics.win_rate) if metrics.win_rate is not None else None
            )
            final_equity_test = float(metrics.final_equity)
        except Exception as exc:
            log.warning(
                "oos.backtest.failed", rank=rank, error=str(exc)
            )
            sharpe_test = None
            total_return_test = 0.0
            max_dd_test = 0.0
            n_trades_test = 0
            win_rate_test = None
            final_equity_test = initial_cash

        # Verdict per strategia
        sharpe_train = float(snap.sharpe_robust)
        if sharpe_test is None or n_trades_test < 3:
            degradation_pct = None
            verdict = "no_signal"
            reason = (
                f"Test ha generato {n_trades_test} trade — "
                "strategia inattiva fuori campione"
            )
        else:
            if sharpe_train > 0:
                degradation_pct = (
                    (sharpe_test - sharpe_train) / sharpe_train * 100
                )
            else:
                degradation_pct = None

            if (
                sharpe_test >= SHARPE_MIN_TEST
                and (
                    degradation_pct is None
                    or sharpe_test / sharpe_train >= DEGRADATION_ROBUST
                )
            ):
                verdict = "robust"
                reason = (
                    f"Sharpe test {sharpe_test:.2f} regge "
                    f"(train {sharpe_train:.2f}, degradation "
                    f"{degradation_pct:+.0f}% se positivo)"
                )
            elif sharpe_test >= 0:
                verdict = "mixed"
                reason = (
                    f"Sharpe test {sharpe_test:.2f} positivo ma degradato "
                    f"({degradation_pct:+.0f}% vs train {sharpe_train:.2f})"
                )
            else:
                verdict = "overfit"
                reason = (
                    f"Sharpe test {sharpe_test:.2f} negativo "
                    f"(train {sharpe_train:.2f}) — strategia non generalizza"
                )

        strategy_results.append(
            OosStrategyResult(
                rank=rank,
                chromosome=dict(snap.chromosome),
                sharpe_train=sharpe_train,
                max_drawdown_train=float(snap.max_drawdown_abs),
                n_trades_train=int(snap.n_trades),
                sharpe_test=sharpe_test,
                total_return_test=total_return_test,
                max_drawdown_test=max_dd_test,
                n_trades_test=n_trades_test,
                win_rate_test=win_rate_test,
                final_equity_test=final_equity_test,
                degradation_pct=degradation_pct,
                verdict=verdict,
                verdict_reason=reason,
            )
        )

    # 6. Verdict aggregato
    n_robust = sum(1 for s in strategy_results if s.verdict == "robust")
    n_mixed = sum(1 for s in strategy_results if s.verdict == "mixed")
    n_overfit = sum(1 for s in strategy_results if s.verdict == "overfit")
    n_no_signal = sum(1 for s in strategy_results if s.verdict == "no_signal")
    total = max(1, len(strategy_results))

    robust_pct = n_robust / total
    if robust_pct >= 0.6:
        overall = "robust"
        overall_reason = (
            f"{n_robust}/{total} strategie ({robust_pct:.0%}) reggono "
            "out-of-sample. Il GA non sembra overfittato."
        )
    elif robust_pct + (n_mixed / total) >= 0.5:
        overall = "mixed"
        overall_reason = (
            f"Solo {n_robust}/{total} robuste, {n_mixed} mixed, {n_overfit} "
            f"overfit. Risultati altalenanti — usa con cautela."
        )
    else:
        overall = "overfit"
        overall_reason = (
            f"Solo {n_robust}/{total} strategie reggono OOS. "
            f"Il GA ha probabilmente memorizzato il training period. "
            "Considera periodo più lungo, range parametri più ampi, "
            "o cambia strategia base."
        )

    return OosResult(
        population_id=population_id,
        strategy_id=cfg.strategy_id,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        train_start=start_train,
        train_end=end_train,
        test_start=start_test,
        test_end=end_test,
        test_days=actual_test_days,
        top_k=len(strategy_results),
        initial_cash=initial_cash,
        strategies=strategy_results,
        evolution_curve=evolution_curve,
        overall_verdict=overall,
        overall_reason=overall_reason,
        n_robust=n_robust,
        n_mixed=n_mixed,
        n_overfit=n_overfit,
        n_no_signal=n_no_signal,
    )
