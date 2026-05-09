"use client";

import type { NewsStats } from "@/lib/api";

interface Props {
  stats: NewsStats | null;
  loading?: boolean;
}

/**
 * Dashboard cards for news pipeline status.
 *
 * Layout: 4 metric cards on desktop, 2x2 grid on mobile, all using Cinzel
 * label + Space Mono value. Sentiment shows color-coded chip (red bearish,
 * green bullish, gold neutral).
 */
export function NewsStatsCards({ stats, loading }: Props) {
  const cards = [
    {
      label: "Total Raw",
      value: stats ? formatInt(stats.total_raw) : "—",
      sub: "ingested news",
    },
    {
      label: "Scored",
      value: stats ? formatInt(stats.total_scored) : "—",
      sub: stats
        ? `${stats.total_raw - stats.total_scored} pending`
        : "—",
    },
    {
      label: "Last 24h",
      value: stats ? formatInt(stats.scored_last_24h) : "—",
      sub: "scored items",
    },
    {
      label: "Sentiment 24h",
      value: stats ? formatSentiment(stats.avg_sentiment_24h) : "—",
      sub: "avg score",
      tone: stats ? sentimentTone(stats.avg_sentiment_24h) : "neutral",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="border border-[--color-surface-border] bg-[--color-surface-card] px-4 py-3"
          style={{
            opacity: loading ? 0.6 : 1,
            transition: "opacity 200ms ease",
          }}
        >
          <p
            className="text-[10px] uppercase text-[--color-text-secondary]"
            style={{
              fontFamily: "var(--font-serif)",
              letterSpacing: "0.25em",
            }}
          >
            {c.label}
          </p>
          <p
            className="mt-2 text-2xl"
            style={{
              fontFamily: "var(--font-mono)",
              color:
                c.tone === "bullish"
                  ? "var(--color-common, #00ff99)"
                  : c.tone === "bearish"
                    ? "var(--color-crimson, #e63946)"
                    : "var(--color-gold)",
              letterSpacing: "0.05em",
            }}
          >
            {c.value}
          </p>
          <p className="mt-1 text-xs text-[--color-text-muted]">{c.sub}</p>
        </div>
      ))}
    </div>
  );
}

function formatInt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

function formatSentiment(s: number): string {
  if (s === 0) return "0.00";
  return (s > 0 ? "+" : "") + s.toFixed(2);
}

function sentimentTone(s: number): "bullish" | "bearish" | "neutral" {
  if (s > 0.1) return "bullish";
  if (s < -0.1) return "bearish";
  return "neutral";
}
