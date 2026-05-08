"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EquityPoint } from "@/lib/api";

interface Props {
  points: EquityPoint[];
  initialCash: number;
  height?: number;
}

interface ChartPoint {
  ts: number;
  label: string;
  equity: number;
  drawdown: number;
  drawdownPct: number;
}

export function EquityCurve({ points, initialCash, height = 380 }: Props) {
  const data = useMemo<ChartPoint[]>(() => {
    return points.map((p) => {
      const date = new Date(p.timestamp);
      return {
        ts: date.getTime(),
        label: formatTs(date),
        equity: p.equity,
        drawdown: p.drawdown,
        drawdownPct: p.drawdown * 100,
      };
    });
  }, [points]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        No equity data — backtest non eseguito o fallito.
      </div>
    );
  }

  const equities = data.map((d) => d.equity);
  const minEq = Math.min(initialCash, ...equities);
  const maxEq = Math.max(initialCash, ...equities);
  const yPad = (maxEq - minEq) * 0.05 || 1;
  const yDomain: [number, number] = [minEq - yPad, maxEq + yPad];

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-gold)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--color-gold)" stopOpacity={0.0} />
            </linearGradient>
          </defs>
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
            domain={yDomain}
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => v.toFixed(0)}
            width={72}
            stroke="var(--color-surface-border)"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              borderRadius: 0,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--color-gold)" }}
            itemStyle={{ color: "var(--color-text-primary)" }}
            formatter={(value: number, name) => {
              if (name === "drawdownPct")
                return [`${value.toFixed(2)}%`, "drawdown"];
              return [value.toFixed(2), name];
            }}
          />
          <ReferenceLine
            y={initialCash}
            stroke="var(--color-text-muted)"
            strokeDasharray="4 4"
            label={{
              value: "initial",
              position: "right",
              fill: "var(--color-text-muted)",
              fontSize: 9,
              fontFamily: "var(--font-mono)",
            }}
          />
          <Area
            type="monotone"
            dataKey="equity"
            name="equity"
            stroke="var(--color-gold)"
            strokeWidth={1.6}
            fill="url(#equityFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatTs(d: Date): string {
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}
