"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { RegimeResponse } from "@/lib/api";

interface Props {
  symbol: string;
  compact?: boolean;
}

const REGIME_COLORS: Record<string, string> = {
  trend_bullish: "#00ff99",
  trend_bearish: "#e63946",
  trend_mixed: "#f4a261",
  range: "#c5a059",
  range_low_vol: "#7799ff",
  range_high_vol: "#bb77ff",
  transition: "#9898a8",
};

export function RegimeBadge({ symbol, compact = false }: Props) {
  const [data, setData] = useState<RegimeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await api.regime(symbol);
        if (!cancelled) {
          setData(r);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "regime load failed");
        }
      }
    };
    load();
    const interval = setInterval(load, 300_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [symbol]);

  if (error || !data) {
    return (
      <span
        className="text-[10px] uppercase tracking-[0.2em]"
        style={{
          color: "var(--color-text-muted)",
          fontFamily: "var(--font-serif)",
        }}
      >
        {symbol} regime: {error ? "—" : "loading…"}
      </span>
    );
  }

  const color = REGIME_COLORS[data.regime] || "var(--color-gold)";
  const labelText = data.regime.replace(/_/g, " ");

  if (compact) {
    return (
      <span
        className="inline-flex items-baseline gap-2 border px-2 py-0.5 text-[11px]"
        style={{
          borderColor: color,
          color,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.05em",
          background: "rgba(8, 2, 16, 0.4)",
        }}
        title={data.notes}
      >
        <span
          className="text-[9px] uppercase tracking-[0.2em]"
          style={{ fontFamily: "var(--font-serif)", opacity: 0.85 }}
        >
          {data.symbol.split("/")[0]} 1d
        </span>
        <span>{labelText}</span>
        <span className="text-[9px]" style={{ opacity: 0.6 }}>
          ADX {data.adx.toFixed(0)} · {data.atr_pct.toFixed(1)}% ·{" "}
          {(data.confidence * 100).toFixed(0)}%
        </span>
      </span>
    );
  }

  return (
    <div
      className="border px-4 py-3"
      style={{
        borderColor: color,
        background: "var(--color-surface-card)",
      }}
    >
      <p
        className="text-[10px] uppercase tracking-[0.3em]"
        style={{
          fontFamily: "var(--font-serif)",
          color: "var(--color-text-secondary)",
        }}
      >
        {data.symbol} · 1D Regime
      </p>
      <p
        className="mt-1 text-2xl"
        style={{
          fontFamily: "var(--font-mono)",
          color,
          letterSpacing: "0.05em",
        }}
      >
        {labelText}
      </p>
      <p className="mt-1 text-[11px] text-[--color-text-muted]">
        Confidence {(data.confidence * 100).toFixed(0)}%
      </p>
      <div
        className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <span className="text-[--color-text-muted]">ADX(14)</span>
        <span className="text-right text-[--color-text-primary]">
          {data.adx.toFixed(2)}
        </span>
        <span className="text-[--color-text-muted]">ATR %</span>
        <span className="text-right text-[--color-text-primary]">
          {data.atr_pct.toFixed(2)}%
        </span>
        <span className="text-[--color-text-muted]">SMA50 slope</span>
        <span className="text-right text-[--color-text-primary]">
          {data.sma_slope_pct >= 0 ? "+" : ""}
          {data.sma_slope_pct.toFixed(2)}%
        </span>
        <span className="text-[--color-text-muted]">RSI(14)</span>
        <span className="text-right text-[--color-text-primary]">
          {data.rsi.toFixed(1)}
        </span>
      </div>
      <p
        className="mt-3 text-[11px] italic"
        style={{
          color: "var(--color-text-secondary)",
          lineHeight: 1.5,
        }}
      >
        {data.notes}
      </p>
    </div>
  );
}
