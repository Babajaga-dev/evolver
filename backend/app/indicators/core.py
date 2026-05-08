"""Registry e dispatch degli indicatori tecnici.

Aggiungere un nuovo indicatore = aggiungere un'``IndicatorSpec`` e una
funzione di computo. Il GA della Fase 2 leggerà direttamente dal registry
per scoprire indicatori disponibili e i range dei loro parametri.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pandas_ta_classic as pta

# Tipo del valore restituito dal computo: nome serie → Series
IndicatorOutput = dict[str, pd.Series]


# ---------------------------------------------------------------------------
# ParamSpec / IndicatorSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """Schema di un parametro: nome, default, range/choices, descrizione."""

    name: str
    type: str  # "int" | "float" | "str"
    default: Any
    min: float | int | None = None
    max: float | int | None = None
    choices: tuple[str, ...] | None = None
    description: str = ""

    def validate(self, value: Any) -> Any:
        """Cast + bound check. Raise ``ValueError`` su fallimento."""
        if self.type == "int":
            v = int(value)
        elif self.type == "float":
            v = float(value)
        elif self.type == "str":
            v = str(value)
            if self.choices and v not in self.choices:
                raise ValueError(
                    f"{self.name}={v!r} non valido (choices={self.choices})"
                )
            return v
        else:  # pragma: no cover
            raise ValueError(f"ParamSpec type ignoto: {self.type}")

        if self.min is not None and v < self.min:
            raise ValueError(f"{self.name}={v} sotto il minimo {self.min}")
        if self.max is not None and v > self.max:
            raise ValueError(f"{self.name}={v} sopra il massimo {self.max}")
        return v


# Funzione che computa un indicatore: (df, validated_params) -> {name: Series}
ComputeFunc = Callable[[pd.DataFrame, dict[str, Any]], IndicatorOutput]


@dataclass(frozen=True)
class IndicatorSpec:
    """Definizione di un indicatore: id, params, kind, output cols."""

    id: str  # es. "rsi", "macd"
    label: str  # human-readable
    kind: str  # "overlay" (sul prezzo) | "panel" (chart separato)
    params: tuple[ParamSpec, ...]
    output_keys: tuple[str, ...]  # nomi serie restituite
    description: str = ""
    fn: ComputeFunc = field(repr=False, default=lambda df, p: {})

    def validate_params(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate+default — params extra sono ignorati (warn-only su LLM
        chiamate, qui filtriamo silenziosi)."""
        out: dict[str, Any] = {}
        for spec in self.params:
            if spec.name in raw and raw[spec.name] is not None:
                out[spec.name] = spec.validate(raw[spec.name])
            else:
                out[spec.name] = spec.default
        return out


# ---------------------------------------------------------------------------
# Compute helpers (pandas_ta_classic shim)
# ---------------------------------------------------------------------------


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Garantisce colonne ``open/high/low/close/volume`` (case-sensitive)."""
    expected = {"open", "high", "low", "close", "volume"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame OHLCV manca colonne: {missing}")
    return df


def _rsi(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    series = pta.rsi(df["close"], length=p["period"])
    return {"rsi": series}


def _ema(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    series = pta.ema(df["close"], length=p["period"])
    return {"ema": series}


def _sma(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    series = pta.sma(df["close"], length=p["period"])
    return {"sma": series}


def _macd(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    out = pta.macd(df["close"], fast=p["fast"], slow=p["slow"], signal=p["signal"])
    if out is None or out.empty:
        return {"macd": pd.Series(dtype=float), "signal": pd.Series(dtype=float),
                "histogram": pd.Series(dtype=float)}
    # pandas_ta_classic colonne: MACD_x_y_z, MACDs_x_y_z, MACDh_x_y_z
    macd_col = next(c for c in out.columns if c.startswith("MACD_"))
    signal_col = next(c for c in out.columns if c.startswith("MACDs_"))
    hist_col = next(c for c in out.columns if c.startswith("MACDh_"))
    return {
        "macd": out[macd_col],
        "signal": out[signal_col],
        "histogram": out[hist_col],
    }


def _bbands(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    out = pta.bbands(df["close"], length=p["period"], std=p["std"])
    if out is None or out.empty:
        return {"lower": pd.Series(dtype=float), "middle": pd.Series(dtype=float),
                "upper": pd.Series(dtype=float)}
    lower_col = next(c for c in out.columns if c.startswith("BBL_"))
    middle_col = next(c for c in out.columns if c.startswith("BBM_"))
    upper_col = next(c for c in out.columns if c.startswith("BBU_"))
    return {
        "lower": out[lower_col],
        "middle": out[middle_col],
        "upper": out[upper_col],
    }


def _atr(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    series = pta.atr(df["high"], df["low"], df["close"], length=p["period"])
    return {"atr": series}


def _adx(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    out = pta.adx(df["high"], df["low"], df["close"], length=p["period"])
    if out is None or out.empty:
        return {"adx": pd.Series(dtype=float), "dmp": pd.Series(dtype=float),
                "dmn": pd.Series(dtype=float)}
    adx_col = next(c for c in out.columns if c.startswith("ADX_"))
    dmp_col = next(c for c in out.columns if c.startswith("DMP_"))
    dmn_col = next(c for c in out.columns if c.startswith("DMN_"))
    return {
        "adx": out[adx_col],
        "dmp": out[dmp_col],
        "dmn": out[dmn_col],
    }


def _stoch(df: pd.DataFrame, p: dict[str, Any]) -> IndicatorOutput:
    out = pta.stoch(
        df["high"], df["low"], df["close"],
        k=p["k"], d=p["d"], smooth_k=p["smooth_k"],
    )
    if out is None or out.empty:
        return {"k": pd.Series(dtype=float), "d": pd.Series(dtype=float)}
    k_col = next(c for c in out.columns if c.startswith("STOCHk_"))
    d_col = next(c for c in out.columns if c.startswith("STOCHd_"))
    return {"k": out[k_col], "d": out[d_col]}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {
    "rsi": IndicatorSpec(
        id="rsi",
        label="RSI",
        kind="panel",
        params=(
            ParamSpec("period", "int", default=14, min=2, max=200,
                      description="Numero di periodi per il calcolo"),
        ),
        output_keys=("rsi",),
        description="Relative Strength Index — momentum oscillator (0-100).",
        fn=_rsi,
    ),
    "ema": IndicatorSpec(
        id="ema",
        label="EMA",
        kind="overlay",
        params=(
            ParamSpec("period", "int", default=50, min=2, max=500),
        ),
        output_keys=("ema",),
        description="Exponential Moving Average.",
        fn=_ema,
    ),
    "sma": IndicatorSpec(
        id="sma",
        label="SMA",
        kind="overlay",
        params=(
            ParamSpec("period", "int", default=50, min=2, max=500),
        ),
        output_keys=("sma",),
        description="Simple Moving Average.",
        fn=_sma,
    ),
    "macd": IndicatorSpec(
        id="macd",
        label="MACD",
        kind="panel",
        params=(
            ParamSpec("fast", "int", default=12, min=2, max=100),
            ParamSpec("slow", "int", default=26, min=3, max=200),
            ParamSpec("signal", "int", default=9, min=2, max=50),
        ),
        output_keys=("macd", "signal", "histogram"),
        description="Moving Average Convergence/Divergence.",
        fn=_macd,
    ),
    "bbands": IndicatorSpec(
        id="bbands",
        label="Bollinger Bands",
        kind="overlay",
        params=(
            ParamSpec("period", "int", default=20, min=2, max=200),
            ParamSpec("std", "float", default=2.0, min=0.5, max=5.0),
        ),
        output_keys=("lower", "middle", "upper"),
        description="Bollinger Bands — middle (SMA) ± std·sigma.",
        fn=_bbands,
    ),
    "atr": IndicatorSpec(
        id="atr",
        label="ATR",
        kind="panel",
        params=(
            ParamSpec("period", "int", default=14, min=2, max=100),
        ),
        output_keys=("atr",),
        description="Average True Range — volatility.",
        fn=_atr,
    ),
    "adx": IndicatorSpec(
        id="adx",
        label="ADX",
        kind="panel",
        params=(
            ParamSpec("period", "int", default=14, min=2, max=100),
        ),
        output_keys=("adx", "dmp", "dmn"),
        description="Average Directional Index — trend strength.",
        fn=_adx,
    ),
    "stoch": IndicatorSpec(
        id="stoch",
        label="Stochastic",
        kind="panel",
        params=(
            ParamSpec("k", "int", default=14, min=2, max=100),
            ParamSpec("d", "int", default=3, min=1, max=50),
            ParamSpec("smooth_k", "int", default=3, min=1, max=50),
        ),
        output_keys=("k", "d"),
        description="Stochastic Oscillator (%K, %D).",
        fn=_stoch,
    ),
}


# Type alias per export
Indicator = IndicatorSpec


def available_indicators() -> list[IndicatorSpec]:
    """Lista degli indicatori registrati."""
    return list(INDICATOR_REGISTRY.values())


def get_indicator(indicator_id: str) -> IndicatorSpec:
    """Ritorna la spec di un indicatore o solleva ``KeyError``."""
    if indicator_id not in INDICATOR_REGISTRY:
        raise KeyError(
            f"Indicatore '{indicator_id}' sconosciuto. "
            f"Disponibili: {sorted(INDICATOR_REGISTRY)}"
        )
    return INDICATOR_REGISTRY[indicator_id]


def compute(
    indicator_id: str,
    df: pd.DataFrame,
    params: dict[str, Any] | None = None,
) -> tuple[IndicatorOutput, dict[str, Any]]:
    """Compute pubblica: validate params + run.

    Returns:
        Tuple ``(output_series, validated_params)``.
    """
    spec = get_indicator(indicator_id)
    df = _ensure_columns(df)
    validated = spec.validate_params(params or {})
    out = spec.fn(df, validated)
    return out, validated
