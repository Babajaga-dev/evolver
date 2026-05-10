"""Registry di strategie preset (cromosoma vincolato pre-Fase 2).

Ogni strategia espone una funzione ``signals(df, params) -> (entries, exits)``
che ritorna due ``pd.Series[bool]`` indicizzate sullo stesso index di ``df``.

Per la Fase 2, il GA evolverà i parametri (range definiti in ``StrategySpec``)
ma manterrà la stessa interfaccia. Aggiungere nuove strategie qui = renderle
immediatamente disponibili al backtest engine e al GA.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.indicators.core import ParamSpec, compute as compute_indicator


SignalsFn = Callable[[pd.DataFrame, dict[str, Any]], tuple[pd.Series, pd.Series]]


@dataclass(frozen=True)
class StrategySpec:
    """Definizione di una strategia parametrica."""

    id: str
    label: str
    family: str  # "trend_follow" | "mean_reversion" | "breakout" | "volatility"
    description: str
    params: tuple[ParamSpec, ...]
    fn: SignalsFn = field(repr=False, default=lambda df, p: (pd.Series(dtype=bool), pd.Series(dtype=bool)))

    def validate_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for spec in self.params:
            if spec.name in raw and raw[spec.name] is not None:
                out[spec.name] = spec.validate(raw[spec.name])
            else:
                out[spec.name] = spec.default
        return out


# ---------------------------------------------------------------------------
# Strategy implementations
# ---------------------------------------------------------------------------


def _rsi_mean_reversion(
    df: pd.DataFrame, p: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    """RSI mean reversion: entry quando RSI < buy_below, exit quando RSI > sell_above."""
    rsi_out, _ = compute_indicator("rsi", df, {"period": p["rsi_period"]})
    rsi = rsi_out["rsi"]
    entries = rsi < p["buy_below"]
    exits = rsi > p["sell_above"]
    return entries.fillna(False), exits.fillna(False)


def _ema_cross(
    df: pd.DataFrame, p: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    """EMA cross: entry su fast > slow (golden), exit su fast < slow (death)."""
    fast_out, _ = compute_indicator("ema", df, {"period": p["fast"]})
    slow_out, _ = compute_indicator("ema", df, {"period": p["slow"]})
    fast = fast_out["ema"]
    slow = slow_out["ema"]
    above = fast > slow
    # Cross-up: era sotto, ora sopra
    entries = above & (~above.shift(1, fill_value=False))
    # Cross-down: era sopra, ora sotto
    exits = (~above) & (above.shift(1, fill_value=False))
    # Le prime N candele EMA hanno NaN → fillna(False) per coerenza con
    # le altre strategie e con vectorbt (NaN booleani sono problematici)
    return entries.fillna(False), exits.fillna(False)


def _macd_cross(
    df: pd.DataFrame, p: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    """MACD cross: entry su MACD > signal con cross-up, exit su cross-down."""
    macd_out, _ = compute_indicator(
        "macd",
        df,
        {"fast": p["fast"], "slow": p["slow"], "signal": p["signal"]},
    )
    macd = macd_out["macd"]
    signal = macd_out["signal"]
    above = macd > signal
    entries = above & (~above.shift(1, fill_value=False))
    exits = (~above) & (above.shift(1, fill_value=False))
    return entries.fillna(False), exits.fillna(False)


def _bb_breakout(
    df: pd.DataFrame, p: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    """Bollinger breakout: entry su close > upper, exit su close < middle."""
    bb_out, _ = compute_indicator(
        "bbands", df, {"period": p["period"], "std": p["std"]}
    )
    upper = bb_out["upper"]
    middle = bb_out["middle"]
    close = df["close"]
    entries = close > upper
    exits = close < middle
    return entries.fillna(False), exits.fillna(False)



def _rsi_macd_combo(
    df: pd.DataFrame, p: dict[str, Any]
) -> tuple[pd.Series, pd.Series]:
    """RSI mean-reversion + MACD trend filter.

    Long quando: RSI < buy_below AND MACD line > signal line (trend bullish).
    Exit quando: RSI > sell_above OR MACD line < signal line (trend bearish).

    Più selettivo del puro RSI: il MACD filter evita di comprare dip in
    bear sostenuti (es. crash 2022) dove RSI < 30 ma il trend continua
    a scendere.
    """
    rsi_out, _ = compute_indicator("rsi", df, {"period": p["rsi_period"]})
    macd_out, _ = compute_indicator(
        "macd",
        df,
        {
            "fast": p["macd_fast"],
            "slow": p["macd_slow"],
            "signal": p["macd_signal"],
        },
    )
    rsi = rsi_out["rsi"]
    macd = macd_out["macd"]
    signal = macd_out["signal"]
    macd_bullish = macd > signal
    macd_bearish = macd < signal

    entries = (rsi < p["buy_below"]) & macd_bullish
    exits = (rsi > p["sell_above"]) | macd_bearish
    return entries.fillna(False), exits.fillna(False)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "rsi_mean_reversion": StrategySpec(
        id="rsi_mean_reversion",
        label="RSI Mean Reversion",
        family="mean_reversion",
        description=(
            "Entry long quando RSI scende sotto la soglia 'buy_below', exit "
            "quando RSI sale sopra 'sell_above'. Strategia controtrend, "
            "efficace in mercati range-bound."
        ),
        params=(
            # period 8-50: 5-7 era troppo reattivo (rumore puro). Postmortem
            # 2026-05-09 ha rilevato GA collapsato su rsi_period=9 in tutte
            # le top 10 -> forziamo minimo 8 per evitare convergenza degenere.
            ParamSpec("rsi_period", "int", default=14, min=8, max=50),
            ParamSpec("buy_below", "float", default=30.0, min=15.0, max=40.0),
            # sell_above esteso a 55 per dare più spazio di fuga al GA
            ParamSpec("sell_above", "float", default=70.0, min=55.0, max=85.0),
        ),
        fn=_rsi_mean_reversion,
    ),
    "ema_cross": StrategySpec(
        id="ema_cross",
        label="EMA Cross",
        family="trend_follow",
        description=(
            "Golden cross / death cross su due EMA. Entry quando la fast "
            "incrocia al rialzo la slow, exit al cross-down. Classico trend "
            "follow, lag intrinseco. Constraint: fast < slow."
        ),
        params=(
            ParamSpec("fast", "int", default=12, min=5, max=50),
            ParamSpec("slow", "int", default=26, min=20, max=200),
        ),
        fn=_ema_cross,
    ),
    "macd_cross": StrategySpec(
        id="macd_cross",
        label="MACD Cross",
        family="trend_follow",
        description=(
            "MACD line vs signal line. Entry su cross-up, exit su cross-down. "
            "Più reattivo dell'EMA cross. Constraint: fast < slow."
        ),
        params=(
            ParamSpec("fast", "int", default=12, min=5, max=30),
            ParamSpec("slow", "int", default=26, min=15, max=80),
            ParamSpec("signal", "int", default=9, min=3, max=20),
        ),
        fn=_macd_cross,
    ),
    "bb_breakout": StrategySpec(
        id="bb_breakout",
        label="Bollinger Breakout",
        family="breakout",
        description=(
            "Breakout della upper band Bollinger come entry, ritorno alla "
            "middle (SMA) come exit. Trend continuation in regime di "
            "espansione di volatilità."
        ),
        params=(
            ParamSpec("period", "int", default=20, min=10, max=50),
            ParamSpec("std", "float", default=2.0, min=1.0, max=3.5),
        ),
        fn=_bb_breakout,
    ),
    "rsi_macd_combo": StrategySpec(
        id="rsi_macd_combo",
        label="RSI + MACD Combo",
        family="mean_reversion",
        description=(
            "Multi-indicatore: RSI mean-reversion con filtro di trend MACD. "
            "Long quando RSI<buy_below AND MACD line > signal line. Exit "
            "quando RSI>sell_above OR MACD bearish. Più selettivo del puro "
            "RSI — evita dip-buying in bear sostenuti (es. 2022)."
        ),
        params=(
            ParamSpec("rsi_period", "int", default=14, min=8, max=50),
            ParamSpec("buy_below", "float", default=30.0, min=15.0, max=40.0),
            ParamSpec("sell_above", "float", default=70.0, min=55.0, max=85.0),
            ParamSpec("macd_fast", "int", default=12, min=5, max=20),
            ParamSpec("macd_slow", "int", default=26, min=15, max=40),
            ParamSpec("macd_signal", "int", default=9, min=3, max=15),
        ),
        fn=_rsi_macd_combo,
    ),
}


# Constraint logici cross-strategy
def has_invalid_constraint(strategy_id: str, params: dict[str, object]) -> bool:
    """Ritorna True se i parametri violano un constraint logico (es. fast >= slow).

    Su TypeError/ValueError → True (constraint INVALIDO): un cromosoma con
    tipi sbagliati è di fatto rotto, non vogliamo che passi il filtro.
    Bug fix dal precedente "return False" che lasciava passare malformed
    come validi.
    """
    if strategy_id in {"ema_cross", "macd_cross"}:
        fast = params.get("fast")
        slow = params.get("slow")
        if fast is None or slow is None:
            return True  # missing params = constraint violato
        try:
            return int(fast) >= int(slow)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return True  # type errato = constraint violato
    if strategy_id == "rsi_macd_combo":
        fast = params.get("macd_fast")
        slow = params.get("macd_slow")
        if fast is None or slow is None:
            return True
        try:
            return int(fast) >= int(slow)
        except (TypeError, ValueError):
            return True
    return False


def available_strategies() -> list[StrategySpec]:
    return list(STRATEGY_REGISTRY.values())


def get_strategy(strategy_id: str) -> StrategySpec:
    if strategy_id not in STRATEGY_REGISTRY:
        raise KeyError(
            f"Strategia '{strategy_id}' sconosciuta. "
            f"Disponibili: {sorted(STRATEGY_REGISTRY)}"
        )
    return STRATEGY_REGISTRY[strategy_id]
