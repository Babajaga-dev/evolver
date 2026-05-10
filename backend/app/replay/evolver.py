"""GA evolver per il Council multi-indicator × multi-TF.

Versione semplificata che usa pymoo MixedVariableProblem direttamente.
Restituisce il miglior CouncilParams trovato + metriche di training.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.core.problem import ElementwiseProblem
from pymoo.core.mixed import MixedVariableGA
from pymoo.operators.crossover.sbx import SBX
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from app.core.logging import get_logger
from app.replay import council as council_mod
from app.replay import genome as genome_mod
from app.replay.runner_backtest import backtest_council_static

log = get_logger(__name__)


class _CouncilProblem(ElementwiseProblem):
    def __init__(
        self,
        *,
        candles_by_tf: dict,
        regime_series: pd.Series,
        initial_cash: float,
        fee: float,
        slippage_bps: float,
    ):
        super().__init__(
            vars=genome_mod.pymoo_vars_for_council(),
            n_obj=2,
            n_constr=0,
        )
        self.candles_by_tf = candles_by_tf
        self.regime_series = regime_series
        self.initial_cash = initial_cash
        self.fee = fee
        self.slippage_bps = slippage_bps

    def _evaluate(self, x: dict, out: dict, *args, **kwargs):
        # Constraint check (soft penalty)
        if genome_mod.has_invalid_constraint(x):
            out["F"] = [10.0, 1.0]  # penalty
            return
        try:
            council = genome_mod.decode_to_council(x)
            r = backtest_council_static(
                candles_by_tf=self.candles_by_tf,
                regime_series=self.regime_series,
                council=council,
                initial_cash=self.initial_cash,
                fee=self.fee,
                slippage_bps=self.slippage_bps,
            )
            # Obiettivi: minimizzare -sharpe e max_drawdown_abs
            sharpe = float(r.get("sharpe", 0.0))
            dd = float(abs(r.get("max_drawdown", 0.0)))
            n_trades = int(r.get("n_trades", 0))
            # Penalty bassa attività
            if n_trades < 3:
                sharpe -= 1.0
            out["F"] = [-sharpe, dd]
        except Exception as exc:
            log.warning("evolver.eval_failed", error=str(exc))
            out["F"] = [10.0, 1.0]


async def evolve_council(
    *,
    candles_by_tf: dict,
    regime_series: pd.Series,
    pop_size: int = 20,
    generations: int = 8,
    initial_cash: float = 10_000.0,
    fee: float = 0.0004,
    slippage_bps: float = 5.0,
) -> tuple[council_mod.CouncilParams, dict]:
    """Run GA per pop_size individui × generations gen. Ritorna best + metriche."""
    problem = _CouncilProblem(
        candles_by_tf=candles_by_tf,
        regime_series=regime_series,
        initial_cash=initial_cash,
        fee=fee,
        slippage_bps=slippage_bps,
    )
    algo = MixedVariableGA(pop_size=pop_size)
    term = get_termination("n_gen", generations)

    import asyncio
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None,
        lambda: minimize(problem, algo, term, seed=42, verbose=False, save_history=False),
    )

    # Best solution: minor -sharpe
    if res.F is None or len(res.F) == 0:
        return council_mod.default_council_params(), {
            "sharpe_train": 0.0, "max_dd_train": 0.0, "diversity": 0.0, "n_trades_train": 0,
        }
    # Sort by -sharpe (col 0)
    F = res.F if res.F.ndim == 2 else res.F.reshape(1, -1)
    X = res.X if isinstance(res.X, (list, np.ndarray)) else [res.X]
    if hasattr(res.X, "shape") and res.X.ndim == 2:
        X = list(res.X)
    elif isinstance(res.X, dict):
        X = [res.X]

    best_idx = int(np.argmin(F[:, 0]))
    best_x = X[best_idx] if best_idx < len(X) else X[0]
    if not isinstance(best_x, dict):
        try:
            best_x = dict(best_x)
        except Exception:
            best_x = X[0]
    best_council = genome_mod.decode_to_council(best_x)
    # Re-eval per metriche
    final_r = backtest_council_static(
        candles_by_tf=candles_by_tf,
        regime_series=regime_series,
        council=best_council,
        initial_cash=initial_cash,
        fee=fee,
        slippage_bps=slippage_bps,
    )
    # Diversity = std degli sharpe del Pareto front
    diversity = float(np.std(-F[:, 0])) if F.shape[0] > 1 else 0.0
    return best_council, {
        "sharpe_train": float(final_r.get("sharpe", 0.0)),
        "max_dd_train": float(final_r.get("max_drawdown", 0.0)),
        "diversity": diversity,
        "n_trades_train": int(final_r.get("n_trades", 0)),
        "pareto_size": int(F.shape[0]),
    }
