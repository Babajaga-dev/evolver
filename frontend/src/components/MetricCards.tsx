"use client";

import type { BacktestMetrics } from "@/lib/api";

interface Props {
  metrics: BacktestMetrics;
}

export function MetricCards({ metrics }: Props) {
  const cards: { label: string; value: string; tone: "good" | "bad" | "neutral" }[] = [
    {
      label: "Total Return",
      value: pct(metrics.total_return),
      tone: metrics.total_return >= 0 ? "good" : "bad",
    },
    {
      label: "Sharpe",
      value: nullable(metrics.sharpe, 2),
      tone: tone(metrics.sharpe, 0.5),
    },
    {
      label: "Calmar",
      value: nullable(metrics.calmar, 2),
      tone: tone(metrics.calmar, 0.5),
    },
    {
      label: "Max DD",
      value: pct(metrics.max_drawdown),
      tone: metrics.max_drawdown > -0.15 ? "good" : "bad",
    },
    {
      label: "Win Rate",
      value: metrics.win_rate !== null ? `${(metrics.win_rate * 100).toFixed(1)}%` : "—",
      tone:
        metrics.win_rate === null
          ? "neutral"
          : metrics.win_rate >= 0.5
            ? "good"
            : "bad",
    },
    {
      label: "Profit Factor",
      value: nullable(metrics.profit_factor, 2),
      tone: tone(metrics.profit_factor, 1.5),
    },
    {
      label: "# Trades",
      value: String(metrics.n_trades),
      tone: "neutral",
    },
    {
      label: "Final Equity",
      value: metrics.final_equity.toLocaleString("en-US", {
        maximumFractionDigits: 0,
      }),
      tone: "neutral",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="border border-[--color-surface-border] bg-[--color-surface-card] p-4"
        >
          <div
            className="mb-1 text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            {c.label}
          </div>
          <div
            className="font-mono text-xl"
            style={{ color: toneColor(c.tone) }}
          >
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function pct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

function nullable(v: number | null, digits: number): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

function tone(v: number | null, threshold: number): "good" | "bad" | "neutral" {
  if (v === null || !Number.isFinite(v)) return "neutral";
  return v >= threshold ? "good" : "bad";
}

function toneColor(t: "good" | "bad" | "neutral"): string {
  switch (t) {
    case "good":
      return "var(--color-gold)";
    case "bad":
      return "var(--color-crimson)";
    default:
      return "var(--color-text-primary)";
  }
}
