"use client";

import { useEffect, useState } from "react";

import { ApiError, api, type AssetSentiment } from "@/lib/api";

interface Props {
  asset: string; // "BTC", "ETH", ...
  hours?: number;
  compact?: boolean; // compact = solo chip, full = card con breakdown
}

/**
 * Badge sentiment news per un asset — usato in /population per mostrare
 * il "regime macro" attuale e in /news come summary card.
 *
 * Auto-refresh ogni 60s. Mostra weighted_signal con colore green/red/gold,
 * count news, evento dominante.
 */
export function SentimentBadge({ asset, hours = 24, compact = false }: Props) {
  const [data, setData] = useState<AssetSentiment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await api.assetSentiment(asset, hours);
        if (!cancelled) {
          setData(r);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof ApiError ? e.message : "load failed");
        }
      }
    };
    load();
    const interval = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [asset, hours]);

  if (error) {
    return (
      <span
        className="text-[10px] uppercase tracking-[0.2em]"
        style={{
          color: "var(--color-text-muted)",
          fontFamily: "var(--font-serif)",
        }}
      >
        {asset} sentiment: —
      </span>
    );
  }

  if (!data) {
    return (
      <span
        className="text-[10px] uppercase tracking-[0.2em]"
        style={{
          color: "var(--color-text-muted)",
          fontFamily: "var(--font-serif)",
        }}
      >
        {asset} sentiment: loading…
      </span>
    );
  }

  const signal = data.weighted_signal;
  const tone =
    signal > 0.15 ? "bullish" : signal < -0.15 ? "bearish" : "neutral";
  const color =
    tone === "bullish"
      ? "#00ff99"
      : tone === "bearish"
        ? "#e63946"
        : "var(--color-gold)";
  const sign = signal > 0 ? "+" : "";

  if (compact) {
    return (
      <span
        className="inline-flex items-baseline gap-1.5 border px-2 py-0.5 text-[11px]"
        style={{
          borderColor: color,
          color,
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.05em",
          background: "rgba(8, 2, 16, 0.4)",
        }}
        title={`${data.n_news} news • avg conf ${(data.avg_confidence * 100).toFixed(0)}% • factual ${(data.avg_factual_impact * 100).toFixed(0)}%`}
      >
        <span
          className="text-[9px] uppercase tracking-[0.2em]"
          style={{ fontFamily: "var(--font-serif)", opacity: 0.85 }}
        >
          {data.asset}
        </span>
        <span>
          {sign}
          {signal.toFixed(2)}
        </span>
        <span
          className="text-[9px]"
          style={{ opacity: 0.6 }}
        >
          ({data.n_news})
        </span>
      </span>
    );
  }

  // Full card
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
        {data.asset} News Regime · {data.hours}h
      </p>
      <p
        className="mt-1 text-2xl"
        style={{
          fontFamily: "var(--font-mono)",
          color,
          letterSpacing: "0.05em",
        }}
      >
        {sign}
        {signal.toFixed(3)}
      </p>
      <p className="mt-1 text-[11px] text-[--color-text-muted]">
        {data.n_news} news · avg conf{" "}
        {(data.avg_confidence * 100).toFixed(0)}% · factual{" "}
        {(data.avg_factual_impact * 100).toFixed(0)}%
      </p>
      {Object.keys(data.by_event_type).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {Object.entries(data.by_event_type)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 4)
            .map(([type, count]) => (
              <span
                key={type}
                className="border border-[--color-surface-border] px-1.5 py-0.5 text-[9px]"
                style={{
                  fontFamily: "var(--font-mono)",
                  color: "var(--color-text-secondary)",
                  letterSpacing: "0.1em",
                }}
              >
                {type} {count}
              </span>
            ))}
        </div>
      )}
    </div>
  );
}
