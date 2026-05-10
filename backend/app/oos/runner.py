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
from app.ga.chromosome import get_default_chromosome
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
    # Alpha vs baseline (textbook params)
    alpha_vs_baseline: float | None = None  # sharpe_test - sharpe_baseline
    verdict: str = "unknown"  # "robust" | "mixed" | "overfit" | "no_signal"
    verdict_reason: str = "" 


@dataclass
class OosBaseline:
    """Backtest del cromosoma 'textbook' (params di default, no GA)."""

    chromosome: dict[str, Any]
    sharpe_test: float | None
    total_return_test: float
    max_drawdown_test: float
    n_trades_test: int
    win_rate_test: float | None
    final_equity_test: float


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
    baseline: OosBaseline | None = None  # textbook params backtest
    overall_verdict: str = "unknown"  # "robust" | "mixed" | "overfit"
    overall_reason: str = ""
    n_robust: int = 0
    n_mixed: int = 0
    n_overfit: int = 0
    n_no_signal: int = 0
    n_alpha_positive: int = 0  # strategie GA che battono baseline


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
    test_start_days_ago: int | None = None,
    test_end_days_ago: int | None = None,
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
    # Priorità: cfg.train_end_at > completed_at > now
    if cfg.train_end_at is not None:
        end_train = cfg.train_end_at
        if end_train.tzinfo is None:
            end_train = end_train.replace(tzinfo=timezone.utc)
    elif state.completed_at:
        end_train = datetime.fromtimestamp(state.completed_at, tz=timezone.utc)
    else:
        end_train = datetime.now(timezone.utc)
    start_train = end_train - timedelta(days=cfg.period_days)

    now = datetime.now(timezone.utc)
    if test_start_days_ago is not None and test_end_days_ago is not None:
        # Override esplicito: test su periodo storico arbitrario
        start_test = now - timedelta(days=int(test_start_days_ago))
        end_test = now - timedelta(days=int(test_end_days_ago))
        if end_test <= start_test:
            raise OosError(
                f"test_end_days_ago ({test_end_days_ago}) deve essere "
                f"< test_start_days_ago ({test_start_days_ago})"
            )
        actual_test_days = (end_test - start_test).days
    else:
        # Default: subito dopo train_end (capped at now)
        start_test = end_train
        end_test = start_test + timedelta(days=test_days)
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

    # 5a. Baseline backtest: textbook params (no GA optimization)
    # Confronto fondamentale: il GA aggiunge valore o stiamo solo guardando rumore?
    baseline_chrom = get_default_chromosome(cfg.strategy_id)
    baseline_psize = float(baseline_chrom.pop("position_size_pct", 50.0))
    baseline: OosBaseline | None = None
    sharpe_baseline: float | None = None
    try:
        bres = engine.run(
            df=test_df,
            strategy_id=cfg.strategy_id,
            params=baseline_chrom,
            symbol=cfg.symbol,
            timeframe=cfg.timeframe,
            initial_cash=initial_cash,
            position_size_pct=baseline_psize,
        )
        bm = bres.metrics
        sharpe_baseline = bm.sharpe
        baseline = OosBaseline(
            chromosome={**baseline_chrom, "position_size_pct": baseline_psize},
            sharpe_test=bm.sharpe,
            total_return_test=float(bm.total_return),
            max_drawdown_test=float(bm.max_drawdown),
            n_trades_test=int(bm.n_trades),
            win_rate_test=float(bm.win_rate) if bm.win_rate is not None else None,
            final_equity_test=float(bm.final_equity),
        )
        log.info(
            "oos.baseline.computed",
            sharpe=bm.sharpe,
            n_trades=bm.n_trades,
            return_pct=bm.total_return,
        )
    except Exception as exc:
        log.warning("oos.baseline.failed", error=str(exc))

    # 5b. Per ogni strategia: backtest su test period
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

        # Compute alpha vs baseline (textbook params)
        if sharpe_test is not None and sharpe_baseline is not None:
            alpha = sharpe_test - sharpe_baseline
        else:
            alpha = None

        # Verdict per strategia (alpha-aware)
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

            # NEW LOGIC (Slice GA-vs-Baseline):
            #   ROBUST  = sharpe_test ≥ 0 AND alpha > 0 (GA batte textbook)
            #   MIXED   = sharpe_test ≥ 0 ma alpha ≤ 0 (positivo ma niente alpha)
            #   OVERFIT = sharpe_test < 0
            # Se il baseline non è disponibile, fallback alla logica vecchia.
            if alpha is not None:
                if sharpe_test >= SHARPE_MIN_TEST and alpha > 0:
                    verdict = "robust"
                    reason = (
                        f"Sharpe test {sharpe_test:.2f} batte il baseline "
                        f"{sharpe_baseline:.2f} (alpha {alpha:+.2f}) — "
                        f"il GA aggiunge valore."
                    )
                elif sharpe_test >= 0:
                    verdict = "mixed"
                    reason = (
                        f"Sharpe test {sharpe_test:.2f} positivo MA non "
                        f"batte il baseline {sharpe_baseline:.2f} "
                        f"(alpha {alpha:+.2f}) — overfit cosmetico."
                    )
                else:
                    verdict = "overfit"
                    reason = (
                        f"Sharpe test {sharpe_test:.2f} negativo "
                        f"(baseline {sharpe_baseline:.2f}, alpha "
                        f"{alpha:+.2f}) — strategia non generalizza."
                    )
            else:
                # Baseline mancante → fallback logica originale
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
                        f"(train {sharpe_train:.2f})"
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
                        f"(train {sharpe_train:.2f})"
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
                alpha_vs_baseline=alpha,
                verdict=verdict,
                verdict_reason=reason,
            )
        )

    # 6. Verdict aggregato (alpha-aware)
    n_robust = sum(1 for s in strategy_results if s.verdict == "robust")
    n_mixed = sum(1 for s in strategy_results if s.verdict == "mixed")
    n_overfit = sum(1 for s in strategy_results if s.verdict == "overfit")
    n_no_signal = sum(1 for s in strategy_results if s.verdict == "no_signal")
    n_alpha_positive = sum(
        1 for s in strategy_results
        if s.alpha_vs_baseline is not None and s.alpha_vs_baseline > 0
    )
    total = max(1, len(strategy_results))
    bs = f"{sharpe_baseline:.2f}" if sharpe_baseline is not None else "n/a"

    robust_pct = n_robust / total
    alpha_pct = n_alpha_positive / total
    if robust_pct >= 0.6:
        overall = "robust"
        overall_reason = (
            f"{n_robust}/{total} strategie ({robust_pct:.0%}) battono il "
            f"baseline {bs} con sharpe positivo. Il GA aggiunge valore "
            f"reale — non è solo overfit cosmetico."
        )
    elif alpha_pct >= 0.5:
        overall = "mixed"
        overall_reason = (
            f"{n_alpha_positive}/{total} strategie battono il baseline {bs} "
            f"ma solo {n_robust} con sharpe ≥ 0. Risultato debole — il GA "
            f"trova marginal alpha ma non è abbastanza solido."
        )
    elif robust_pct + (n_mixed / total) >= 0.5:
        overall = "mixed"
        overall_reason = (
            f"Solo {n_robust}/{total} robuste, {n_mixed} mixed, {n_overfit} "
            f"overfit (baseline {bs}). Risultati altalenanti — usa con cautela."
        )
    else:
        overall = "overfit"
        overall_reason = (
            f"Solo {n_robust}/{total} strategie battono il baseline {bs}. "
            f"Il GA ha memorizzato il training period o non aggiunge valore "
            f"sopra i parametri textbook. Considera periodo più lungo, "
            f"range più ampi, o cambia strategia base."
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
        baseline=baseline,
        overall_verdict=overall,
        overall_reason=overall_reason,
        n_robust=n_robust,
        n_mixed=n_mixed,
        n_overfit=n_overfit,
        n_no_signal=n_no_signal,
        n_alpha_positive=n_alpha_positive,
    )
