"""Cromosoma per il Council multi-indicator × multi-TF.

Strategia di encoding (mantenere il genoma gestibile):
- 4 indicatori × params primari (shared across TF per evitare 60+ dim):
    rsi_period, rsi_buy_below, rsi_sell_above
    macd_fast, macd_slow, macd_signal
    bb_period, bb_std
    ema_fast, ema_slow
  → 10 numeri condivisi tra i 3 TF (semplificazione consapevole — i TF differenti
  vedono le candele con orizzonti differenti, ma i parametri di indicatore sono
  spesso simili. Future slice: TF-specific params se necessario.)
- 7 regimi × 4 indicatori = 28 pesi
- 1 position_size_pct

TOTALE: 10 + 28 + 1 = 39 dim
"""

from __future__ import annotations

from typing import Any

from pymoo.core.variable import Integer, Real

from app.replay.council import INDICATORS, REGIMES, CouncilParams, VoterParams


# Genome layout: nomi e bounds in ordine canonico
GENOME_SPEC: list[tuple[str, str, float, float]] = [
    # indicator params (shared across TF)
    ("rsi_period",      "int",   8.0,  50.0),
    ("rsi_buy_below",   "float", 15.0, 40.0),
    ("rsi_sell_above",  "float", 55.0, 85.0),
    ("macd_fast",       "int",   5.0,  20.0),
    ("macd_slow",       "int",   15.0, 40.0),
    ("macd_signal",     "int",   3.0,  15.0),
    ("bb_period",       "int",   10.0, 40.0),
    ("bb_std",          "float", 1.5,  3.0),
    ("ema_fast",        "int",   5.0,  30.0),
    ("ema_slow",        "int",   20.0, 100.0),
    # position size
    ("position_size_pct", "float", 10.0, 80.0),
]
# Regime × indicator weights (28 dim)
for _r in REGIMES:
    for _i in INDICATORS:
        GENOME_SPEC.append((f"w_{_r}_{_i}", "float", 0.0, 1.0))


def pymoo_vars_for_council() -> dict[str, Any]:
    """Costruisce il dict vars= per MixedVariableProblem di pymoo."""
    out: dict[str, Any] = {}
    for name, kind, lo, hi in GENOME_SPEC:
        if kind == "int":
            out[name] = Integer(bounds=(int(lo), int(hi)))
        else:
            out[name] = Real(bounds=(float(lo), float(hi)))
    return out


def decode_to_council(x: dict[str, Any]) -> CouncilParams:
    """Decodifica un dict cromosoma → CouncilParams pronto per backtest."""
    # 1) Voter params (shared across TFs)
    voter = VoterParams(
        rsi_period=int(x.get("rsi_period", 14)),
        rsi_buy_below=float(x.get("rsi_buy_below", 30.0)),
        rsi_sell_above=float(x.get("rsi_sell_above", 70.0)),
        macd_fast=int(x.get("macd_fast", 12)),
        macd_slow=int(x.get("macd_slow", 26)),
        macd_signal=int(x.get("macd_signal", 9)),
        bb_period=int(x.get("bb_period", 20)),
        bb_std=float(x.get("bb_std", 2.0)),
        ema_fast=int(x.get("ema_fast", 12)),
        ema_slow=int(x.get("ema_slow", 26)),
    )
    # Replicato sui 3 timeframe
    voters = {}
    from app.replay.council import TIMEFRAMES
    for ind in INDICATORS:
        for tf in TIMEFRAMES:
            voters[f"{ind}_{tf}"] = voter

    # 2) Pesi regime × indicatore (normalizzati per regime)
    weights: dict[str, dict[str, float]] = {}
    for r in REGIMES:
        raw = {ind: float(x.get(f"w_{r}_{ind}", 0.25)) for ind in INDICATORS}
        total = sum(raw.values()) + 1e-9
        weights[r] = {ind: raw[ind] / total for ind in INDICATORS}

    # 3) Transition rimane sempre cash (override)
    weights["transition"] = {ind: 0.0 for ind in INDICATORS}

    pos = float(x.get("position_size_pct", 50.0))
    return CouncilParams(voters=voters, weights=weights, position_size_pct=pos)


def encode_from_council(c: CouncilParams) -> dict[str, Any]:
    """Inverse: estrae cromosoma da un CouncilParams (per persist + restore)."""
    # Prendiamo i params dal voter rsi_4h (sono shared comunque)
    v = c.get_voter("rsi", "4h")
    out: dict[str, Any] = {
        "rsi_period": v.rsi_period,
        "rsi_buy_below": v.rsi_buy_below,
        "rsi_sell_above": v.rsi_sell_above,
        "macd_fast": v.macd_fast,
        "macd_slow": v.macd_slow,
        "macd_signal": v.macd_signal,
        "bb_period": v.bb_period,
        "bb_std": v.bb_std,
        "ema_fast": v.ema_fast,
        "ema_slow": v.ema_slow,
        "position_size_pct": c.position_size_pct,
    }
    for r in REGIMES:
        for ind in INDICATORS:
            out[f"w_{r}_{ind}"] = c.get_weight(r, ind)
    return out


def has_invalid_constraint(x: dict[str, Any]) -> bool:
    """Constraint: macd_fast<macd_slow, ema_fast<ema_slow."""
    try:
        if int(x["macd_fast"]) >= int(x["macd_slow"]):
            return True
        if int(x["ema_fast"]) >= int(x["ema_slow"]):
            return True
    except (KeyError, ValueError, TypeError):
        return True
    return False
