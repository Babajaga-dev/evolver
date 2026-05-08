"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { OHLCVCandle } from "@/lib/api";

interface Props {
  candles: OHLCVCandle[];
  height?: number;
}

interface ChartPoint {
  ts: number;
  label: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function PriceChart({ candles, height = 360 }: Props) {
  const data = useMemo<ChartPoint[]>(
    () =>
      candles.map((c) => {
        const date = new Date(c.timestamp);
        return {
          ts: date.getTime(),
          label: formatTs(date),
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
          volume: Number(c.volume),
        };
      }),
    [candles],
  );

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        No data — try a different range or wait for backfill to complete.
      </div>
    );
  }

  const closes = data.map((d) => d.close);
  const minClose = Math.min(...closes);
  const maxClose = Math.max(...closes);
  const yPadding = (maxClose - minClose) * 0.05;
  const yDomain: [number, number] = [
    minClose - yPadding,
    maxClose + yPadding,
  ];

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <defs>
            <linearGradient id="closeFill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="var(--color-btc)"
                stopOpacity={0.5}
              />
              <stop
                offset="100%"
                stopColor="var(--color-btc)"
                stopOpacity={0.0}
              />
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
            tickMargin={6}
            interval="preserveStartEnd"
            minTickGap={48}
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
            width={64}
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
            formatter={(value: number, key) => [value.toFixed(2), key]}
          />
          <Area
            type="monotone"
            dataKey="close"
            stroke="var(--color-btc)"
            strokeWidth={1.5}
            fill="url(#closeFill)"
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
