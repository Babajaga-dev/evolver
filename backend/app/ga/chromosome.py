"""Cromosoma vincolato per il GA — wrap su StrategySpec del registry.

Filosofia v2.0 (Slice iniziale):
    Un cromosoma evolve i parametri di **una singola strategia** (scelta a
    runtime dall'utente quando lancia il GA). L'output è un Pareto front di
    configurazioni di parametri all'interno di quella famiglia, ottimizzata
    su Sharpe robusto vs MaxDD vs complexity.

In v2.1 estenderemo a cross-family GA con strategy_family come Choice
variable, ma richiede MixedVariableGA + handling condizionale dei params
attivi per famiglia. Lo facciamo in slice separato per non bloccare la
prima dimostrazione browser-provable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pymoo.core.variable import Choice, Integer, Real

from app.backtest.strategies import get_strategy
from app.indicators.core import ParamSpec


# ---------------------------------------------------------------------------
# Chromosome spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChromosomeSpec:
    """Definizione completa del cromosoma per il GA.

    Attributes:
        strategy_id: Strategia famiglia (immutabile per il run).
        param_names: Nomi parametri in ordine canonico (per encoding stabile).
        pymoo_vars: Dict ``name → pymoo.Variable`` da passare a ``vars=`` di
            ``MixedVariableProblem``.
    """

    strategy_id: str
    param_names: tuple[str, ...]
    pymoo_vars: dict[str, Any] = field(default_factory=dict)


# Parametri "universali" che si aggiungono a ogni strategia
UNIVERSAL_PARAMS = {
    "position_size_pct": ParamSpec(
        name="position_size_pct",
        type="float",
        default=50.0,
        min=10.0,
        max=100.0,
        description=(
            "% del capitale disponibile per ogni entry (10-100). "
            "100 = all-in, 10 = molto conservativo. Letto da BacktestEngine "
            "come 'size' di vectorbt with size_type='percent'."
        ),
    ),
}


def build_chromosome_spec(strategy_id: str) -> ChromosomeSpec:
    """Costruisce ``ChromosomeSpec`` per una strategia del registry.

    Le pymoo variables vengono derivate dai ``ParamSpec`` di
    ``StrategySpec.params`` + parametri universali.
    """
    spec = get_strategy(strategy_id)

    pymoo_vars: dict[str, Any] = {}
    names: list[str] = []

    for p in spec.params:
        pymoo_vars[p.name] = _to_pymoo_var(p)
        names.append(p.name)

    for p in UNIVERSAL_PARAMS.values():
        pymoo_vars[p.name] = _to_pymoo_var(p)
        names.append(p.name)

    return ChromosomeSpec(
        strategy_id=strategy_id,
        param_names=tuple(names),
        pymoo_vars=pymoo_vars,
    )


def _to_pymoo_var(p: ParamSpec) -> Any:
    """Mappa ``ParamSpec`` → pymoo Variable.

    - int → Integer(min, max)
    - float → Real(min, max)
    - str con choices → Choice(options)
    """
    if p.type == "int":
        if p.min is None or p.max is None:
            raise ValueError(f"ParamSpec int '{p.name}' senza min/max")
        return Integer(bounds=(int(p.min), int(p.max)))
    if p.type == "float":
        if p.min is None or p.max is None:
            raise ValueError(f"ParamSpec float '{p.name}' senza min/max")
        return Real(bounds=(float(p.min), float(p.max)))
    if p.type == "str":
        if not p.choices:
            raise ValueError(f"ParamSpec str '{p.name}' senza choices")
        return Choice(options=list(p.choices))
    raise ValueError(f"ParamSpec type non supportato: {p.type}")


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------


def encode_chromosome(
    params: dict[str, Any],
    spec: ChromosomeSpec,
) -> dict[str, Any]:
    """Filtra e ordina ``params`` secondo lo spec del cromosoma.

    pymoo vuole un dict con tutte e sole le keys dichiarate in ``vars``.
    """
    return {k: params[k] for k in spec.param_names if k in params}


def decode_chromosome(
    x: dict[str, Any],
    spec: ChromosomeSpec,
) -> dict[str, Any]:
    """Decodifica dict pymoo → dict params per BacktestEngine.

    Filtra solo le keys conosciute dallo spec (pymoo a volte aggiunge meta).
    """
    return {k: x[k] for k in spec.param_names if k in x}


# ---------------------------------------------------------------------------
# Default chromosome (baseline / textbook params)
# ---------------------------------------------------------------------------


def get_default_chromosome(strategy_id: str) -> dict[str, Any]:
    """Ritorna il cromosoma 'baseline' (textbook) per una strategia.

    Combina i ParamSpec.default della strategia + UNIVERSAL_PARAMS.default.
    Usato dall'OOS runner per il confronto GA-optimized vs no-optimization.

    Esempio rsi_mean_reversion:
        {"rsi_period": 14, "buy_below": 30.0, "sell_above": 70.0,
         "position_size_pct": 50.0}
    """
    spec = get_strategy(strategy_id)
    out: dict[str, Any] = {}
    for p in spec.params:
        out[p.name] = p.default
    for p in UNIVERSAL_PARAMS.values():
        out[p.name] = p.default
    return out
