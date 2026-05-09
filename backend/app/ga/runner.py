"""GA runner — orchestra pymoo NSGA-II + persistence DB.

Le generazioni vengono persistite incrementalmente così che il frontend
possa fare polling e mostrare progresso live (chart fitness, Pareto, top-N).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.callback import Callback
from pymoo.core.mixed import (
    MixedVariableDuplicateElimination,
    MixedVariableMating,
    MixedVariableSampling,
)
from pymoo.core.problem import ElementwiseProblem
from pymoo.optimize import minimize

from app.core.logging import get_logger
from app.ga.chromosome import (
    ChromosomeSpec,
    build_chromosome_spec,
    decode_chromosome,
)
from app.ga.fitness import FitnessConfig, FitnessResult, compute_fitness


log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class GaConfig:
    """Configurazione di un run GA."""

    strategy_id: str
    symbol: str
    timeframe: str
    period_days: int = 365
    initial_cash: float = 10_000.0
    population_size: int = 30
    n_generations: int = 15
    n_windows: int = 3
    seed: int = 42
    fee: float = 0.001
    slippage_bps: float = 2.0


# ---------------------------------------------------------------------------
# Generation snapshot per polling
# ---------------------------------------------------------------------------


@dataclass
class GenerationSnapshot:
    """Snapshot di una generazione — quello che serve al frontend per chart."""

    generation: int
    best_fitness: float  # neg_sharpe_robust più basso (= miglior Sharpe)
    mean_fitness: float
    worst_fitness: float
    std_fitness: float
    best_sharpe_robust: float
    best_max_dd: float
    diversity: float  # std dei param values normalizzati
    elapsed_seconds: float
    timestamp: float  # unix


@dataclass
class StrategySnapshot:
    """Cromosoma valutato — usato per Pareto e leaderboard."""

    chromosome: dict[str, Any]
    sharpe_robust: float
    max_drawdown_abs: float
    complexity: float
    n_trades: int
    n_windows_winning: int
    generation: int


@dataclass
class RunState:
    """Stato corrente del run, accessibile tramite polling."""

    population_id: str
    config: GaConfig
    status: str = "pending"  # pending | running | completed | failed
    current_generation: int = 0
    started_at: float | None = None
    completed_at: float | None = None
    error: str | None = None
    generations: list[GenerationSnapshot] = field(default_factory=list)
    strategies: list[StrategySnapshot] = field(default_factory=list)


# ---------------------------------------------------------------------------
# pymoo Problem
# ---------------------------------------------------------------------------


class _StrategyOptimizationProblem(ElementwiseProblem):
    """Pymoo ElementwiseProblem per ottimizzare i params di una strategy."""

    def __init__(
        self,
        spec: ChromosomeSpec,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        fitness_config: FitnessConfig,
    ) -> None:
        super().__init__(vars=spec.pymoo_vars, n_obj=3, n_ieq_constr=0)
        self._spec = spec
        self._df = df
        self._symbol = symbol
        self._timeframe = timeframe
        self._fitness_config = fitness_config
        # Cache risultati per inserire in RunState dopo ogni gen
        self._last_evaluations: list[tuple[dict[str, Any], FitnessResult]] = []

    def _evaluate(self, X: dict[str, Any], out: dict[str, Any], *args, **kwargs) -> None:
        params = decode_chromosome(X, self._spec)
        result = compute_fitness(
            chromosome_params=params,
            df=self._df,
            strategy_id=self._spec.strategy_id,
            symbol=self._symbol,
            timeframe=self._timeframe,
            config=self._fitness_config,
        )
        out["F"] = result.objectives
        # Salva l'evaluation per il callback (gen-based dump)
        self._last_evaluations.append((params, result))


# ---------------------------------------------------------------------------
# Pymoo Callback per progress hook
# ---------------------------------------------------------------------------


class _ProgressCallback(Callback):
    """Hook eseguito da pymoo dopo ogni generazione."""

    def __init__(
        self,
        problem: _StrategyOptimizationProblem,
        state: RunState,
        on_generation: Callable[[RunState], None] | None = None,
    ) -> None:
        super().__init__()
        self._problem = problem
        self._state = state
        self._on_generation = on_generation
        self._t0 = time.time()
        self._evals_seen = 0

    def notify(self, algorithm: Any) -> None:
        gen = int(algorithm.n_gen)
        pop = algorithm.pop

        # F dell'intera popolazione (pymoo array Nx3)
        F = pop.get("F")
        if F is None or len(F) == 0:
            return

        f0 = F[:, 0]  # neg_sharpe_robust (lower = better)
        snapshot = GenerationSnapshot(
            generation=gen,
            best_fitness=float(np.min(f0)),
            mean_fitness=float(np.mean(f0)),
            worst_fitness=float(np.max(f0)),
            std_fitness=float(np.std(f0)),
            best_sharpe_robust=float(-np.min(f0)),
            best_max_dd=float(F[np.argmin(f0), 1]),
            diversity=_compute_diversity(pop.get("X")),
            elapsed_seconds=time.time() - self._t0,
            timestamp=time.time(),
        )
        self._state.current_generation = gen
        self._state.generations.append(snapshot)

        # Aggiungi strategy snapshot per i nuovi evaluations
        new_evals = self._problem._last_evaluations[self._evals_seen:]
        for params, fit in new_evals:
            self._state.strategies.append(
                StrategySnapshot(
                    chromosome=_native_dict(params),
                    sharpe_robust=float(fit.sharpe_robust),
                    max_drawdown_abs=float(fit.objectives[1]),
                    complexity=float(fit.objectives[2]),
                    n_trades=int(fit.n_trades_total),
                    n_windows_winning=int(fit.n_windows_winning),
                    generation=int(gen),
                )
            )
        self._evals_seen = len(self._problem._last_evaluations)

        if self._on_generation:
            try:
                self._on_generation(self._state)
            except Exception as exc:  # pragma: no cover
                log.exception("ga.callback.failed", error=str(exc))


def _to_native(value: Any) -> Any:
    """Converte numpy/pandas scalars a Python native types.

    Pydantic v2 non serializza numpy.int64/float64/bool_/etc. nativamente.
    Visto che i chromosome dict finiscono in JSON via FastAPI, dobbiamo
    forzare il cast prima del save.
    """
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _native_dict(d: dict[str, Any]) -> dict[str, Any]:
    """Cast tutti i valori numpy a Python native."""
    return {k: _to_native(v) for k, v in d.items()}


def _compute_diversity(X: Any) -> float:
    """Diversity = mean std dei parametri numerici (dopo normalizzazione naive).

    Per dict-typed pop di pymoo, X è array di dict. Estraiamo solo i valori
    numerici e calcoliamo std.
    """
    if X is None or len(X) == 0:
        return 0.0
    try:
        # pymoo dict-pop ritorna array di dict
        rows = list(X)
        if not rows:
            return 0.0
        # Prendi tutte le keys numeriche del primo dict
        first = rows[0]
        if not isinstance(first, dict):
            return 0.0
        numeric_keys = [
            k for k, v in first.items() if isinstance(v, (int, float))
        ]
        if not numeric_keys:
            return 0.0
        # Stack values
        matrix = np.array(
            [[float(r[k]) for k in numeric_keys] for r in rows]
        )
        # Std per colonna, normalizzato per range
        col_std = matrix.std(axis=0)
        col_range = matrix.max(axis=0) - matrix.min(axis=0) + 1e-9
        normalized = col_std / col_range
        return float(normalized.mean())
    except Exception:  # pragma: no cover
        return 0.0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class GaRunner:
    """Orchestra un run GA completo con persistence/progress hooks."""

    def __init__(
        self,
        config: GaConfig,
        df: pd.DataFrame,
        on_generation: Callable[[RunState], Awaitable[None]] | None = None,
    ) -> None:
        self.config = config
        self.df = df
        self.on_generation_async = on_generation
        self.spec = build_chromosome_spec(config.strategy_id)

    def run_blocking(self, state: RunState) -> RunState:
        """Esegue il GA in modo bloccante. Per uso in thread/async wrapper."""
        state.status = "running"
        state.started_at = time.time()

        problem = _StrategyOptimizationProblem(
            spec=self.spec,
            df=self.df,
            symbol=self.config.symbol,
            timeframe=self.config.timeframe,
            fitness_config=FitnessConfig(
                n_windows=self.config.n_windows,
                initial_cash=self.config.initial_cash,
                fee=self.config.fee,
                slippage_bps=self.config.slippage_bps,
            ),
        )

        # Callback sync per pymoo (no async dentro)
        sync_progress_state: list[RunState] = [state]

        def on_gen_sync(s: RunState) -> None:
            sync_progress_state[0] = s

        callback = _ProgressCallback(
            problem=problem, state=state, on_generation=on_gen_sync
        )

        algorithm = NSGA2(
            pop_size=self.config.population_size,
            sampling=MixedVariableSampling(),
            mating=MixedVariableMating(
                eliminate_duplicates=MixedVariableDuplicateElimination()
            ),
            eliminate_duplicates=MixedVariableDuplicateElimination(),
        )

        try:
            minimize(
                problem,
                algorithm,
                ("n_gen", self.config.n_generations),
                seed=self.config.seed,
                callback=callback,
                verbose=False,
            )
            state.status = "completed"
        except Exception as exc:
            log.exception("ga.run.failed", error=str(exc))
            state.status = "failed"
            state.error = str(exc)
        finally:
            state.completed_at = time.time()

        return state

    async def run_async(self, state: RunState) -> RunState:
        """Wrapper asyncio: esegue il GA in un thread separato così il loop
        FastAPI non si blocca. Periodicamente fa await su un callback async
        per persistenza Redis.

        Nota: il GA gira in thread (vectorbt+pymoo NumPy/numba bound), ma
        usiamo un thread di "saver" parallelo che fa polling sullo state
        ogni 1.5s e lo salva su Redis. Così frontend → Redis è sempre
        max 1.5s indietro rispetto al GA in corso.
        """
        from app.ga import state as state_store

        # Salva subito stato pending
        await state_store.save_state(state)

        # Saver loop: polla state e salva su Redis ogni 1.5s
        stop_event = asyncio.Event()

        async def saver() -> None:
            while not stop_event.is_set():
                try:
                    await state_store.save_state(state)
                except Exception as exc:  # pragma: no cover
                    log.warning("ga.state.save_failed", error=str(exc))
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=1.5)
                except asyncio.TimeoutError:
                    pass

        saver_task = asyncio.create_task(saver())

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.run_blocking, state)
        finally:
            # Salva stato finale + stop saver
            stop_event.set()
            try:
                await asyncio.wait_for(saver_task, timeout=2.0)
            except asyncio.TimeoutError:  # pragma: no cover
                saver_task.cancel()
            await state_store.save_state(state)

        return state
