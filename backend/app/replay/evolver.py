"""Optuna TPE evolver per il Council.

Sostituisce pymoo NSGA-II basandosi su Bayesian vs Evolutionary paper
(Mathematics MDPI 2026): TPE 75% win rate, convergenza 5-7× più veloce.

API identica: n_trials_optuna = pop_size * generations
"""
from __future__ import annotations
import asyncio
import warnings
import numpy as np
import optuna
import pandas as pd

from app.core.logging import get_logger
from app.replay import council as council_mod
from app.replay import genome as genome_mod
from app.replay.runner_backtest import backtest_council_static

log = get_logger(__name__)
optuna.logging.set_verbosity(optuna.logging.WARNING)


def _suggest_chromosome(trial: optuna.Trial) -> dict:
    x: dict = {}
    for name, kind, lo, hi in genome_mod.GENOME_SPEC:
        if kind == "int":
            x[name] = trial.suggest_int(name, int(lo), int(hi))
        else:
            x[name] = trial.suggest_float(name, float(lo), float(hi))
    return x


def _objective_factory(candles_by_tf, regime_series, initial_cash, fee, slippage_bps):
    def objective(trial: optuna.Trial) -> float:
        x = _suggest_chromosome(trial)
        if genome_mod.has_invalid_constraint(x):
            raise optuna.TrialPruned()
        try:
            council = genome_mod.decode_to_council(x)
            r = backtest_council_static(
                candles_by_tf=candles_by_tf, regime_series=regime_series,
                council=council, initial_cash=initial_cash, fee=fee, slippage_bps=slippage_bps,
            )
            sharpe = float(r.get("sharpe", 0.0))
            n_trades = int(r.get("n_trades", 0))
            if n_trades < 3:
                sharpe -= 1.0
            trial.set_user_attr("n_trades", n_trades)
            trial.set_user_attr("max_drawdown", float(r.get("max_drawdown", 0.0)))
            trial.set_user_attr("total_return", float(r.get("total_return", 0.0)))
            return sharpe
        except Exception as exc:
            log.warning("evolver.eval_failed", error=str(exc))
            raise optuna.TrialPruned()
    return objective


async def evolve_council(
    *, candles_by_tf, regime_series, pop_size=20, generations=8,
    initial_cash=10_000.0, fee=0.0004, slippage_bps=5.0,
) -> tuple[council_mod.CouncilParams, dict]:
    n_trials = int(pop_size * generations)
    sampler = optuna.samplers.TPESampler(
        seed=42,
        n_startup_trials=min(10, max(5, n_trials // 5)),
        multivariate=True, group=True,
    )
    study = optuna.create_study(direction="maximize", sampler=sampler, study_name="council_evolution")
    objective = _objective_factory(candles_by_tf, regime_series, initial_cash, fee, slippage_bps)
    loop = asyncio.get_event_loop()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        await loop.run_in_executor(
            None,
            lambda: study.optimize(objective, n_trials=n_trials, show_progress_bar=False),
        )
    if not study.best_trials:
        return council_mod.default_council_params(), {
            "sharpe_train": 0.0, "max_dd_train": 0.0, "diversity": 0.0,
            "n_trades_train": 0, "n_trials_run": 0, "optimizer": "optuna_tpe",
        }
    best = study.best_trial
    best_council = genome_mod.decode_to_council(best.params)
    completed = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    sharpe_values = [float(t.value) for t in completed if t.value is not None]
    diversity = float(np.std(sharpe_values)) if len(sharpe_values) > 1 else 0.0
    log.info("evolver.optuna_complete", n_trials=len(completed), best_sharpe=best.value, diversity=diversity)
    return best_council, {
        "sharpe_train": float(best.value or 0.0),
        "max_dd_train": float(best.user_attrs.get("max_drawdown", 0.0)),
        "diversity": diversity,
        "n_trades_train": int(best.user_attrs.get("n_trades", 0)),
        "n_trials_run": len(completed),
        "optimizer": "optuna_tpe",
    }
