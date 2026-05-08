"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { IndicatorResponse } from "@/lib/api";

interface Props {
  indicator: IndicatorResponse;
  height?: number;
}

interface PanelPoint {
  ts: number;
  label: string;
  [key: string]: number | string | null;
}

const SERIES_COLORS: Record<string, string> = {
  // RSI
  rsi: "#bb77ff",
  // MACD
  macd: "#7799ff",
  signal: "#f4a261",
  histogram: "#5a5a6a",
  // ATR / ADX
  atr: "#7799ff",
  adx: "#f4a261",
  dmp: "#00ff99",
  dmn: "#e63946",
  // Stochastic
  k: "#7799ff",
  d: "#f4a261",
};

/**
 * Pannello "panel" — chart secondario per indicatori che hanno scala
 * diversa dal prezzo (RSI 0-100, MACD intorno a 0, ATR/ADX, Stoch).
 */
export function IndicatorPanel({ indicator, height = 160 }: Props) {
  const data = useMemo<PanelPoint[]>(() => {
    return indicator.points.map((p) => {
      const date = new Date(p.timestamp);
      const point: PanelPoint = {
        ts: date.getTime(),
        label: formatTs(date),
      };
      for (const [key, value] of Object.entries(p.values)) {
        point[key] = value;
      }
      return point;
    });
  }, [indicator]);

  const refLines = referenceLinesFor(indicator.indicator);

  return (
    <div
      className="border border-[--color-surface-border] bg-[--color-surface-card] p-4"
      style={{ width: "100%" }}
    >
      <h3
        className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {indicator.label} {formatParams(indicator.params)}
      </h3>
      <div style={{ width: "100%", height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={data}
            margin={{ top: 4, right: 16, bottom: 4, left: 16 }}
          >
            <CartesianGrid
              strokeDasharray="2 4"
              stroke="var(--color-surface-border)"
            />
            <XAxis
              dataKey="label"
              tick={{
                fill: "var(--color-text-secondary)",
                fontFamily: "var(--font-mono)",
                fontSize: 10,
              }}
              minTickGap={48}
              interval="preserveStartEnd"
              stroke="var(--color-surface-border)"
            />
            <YAxis
              tick={{
                fill: "var(--color-text-secondary)",
                fontFamily: "var(--font-mono)",
                fontSize: 10,
              }}
              tickFormatter={(v) =>
                Math.abs(v) < 1 ? v.toFixed(2) : v.toFixed(1)
              }
              width={64}
              stroke="var(--color-surface-border)"
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "var(--color-surface-card)",
                border: "1px solid var(--color-gold)",
                borderRadius: 0,
                fontFamily: "var(--font-mono)",
                fontSize: 11,
              }}
              labelStyle={{ color: "var(--color-gold)" }}
              itemStyle={{ color: "var(--color-text-primary)" }}
              formatter={(value: number, name) => [
                typeof value === "number" ? value.toFixed(3) : "—",
                name,
              ]}
            />
            {refLines.map((rl) => (
              <ReferenceLine
                key={rl.label}
                y={rl.value}
                stroke={rl.color}
                strokeDasharray="2 4"
                label={{
                  value: rl.label,
                  position: "right",
                  fill: rl.color,
                  fontSize: 9,
                  fontFamily: "var(--font-mono)",
                }}
              />
            ))}
            {indicator.output_keys.map((key) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={SERIES_COLORS[key] ?? "var(--color-gold)"}
                strokeWidth={1.2}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface RefLine {
  value: number;
  label: string;
  color: string;
}

function referenceLinesFor(id: string): RefLine[] {
  switch (id) {
    case "rsi":
      return [
        { value: 30, label: "30 oversold", color: "var(--color-text-muted)" },
        { value: 50, label: "50", color: "var(--color-surface-border)" },
        { value: 70, label: "70 overbought", color: "var(--color-text-muted)" },
      ];
    case "stoch":
      return [
        { value: 20, label: "20 oversold", color: "var(--color-text-muted)" },
        { value: 80, label: "80 overbought", color: "var(--color-text-muted)" },
      ];
    case "macd":
      return [
        { value: 0, label: "0", color: "var(--color-text-muted)" },
      ];
    case "adx":
      return [
        { value: 25, label: "25 trend threshold", color: "var(--color-text-muted)" },
      ];
    default:
      return [];
  }
}

function formatTs(d: Date): string {
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

function formatParams(params: Record<string, number | string>): string {
  const flat = Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  return flat ? `· ${flat}` : "";
}
