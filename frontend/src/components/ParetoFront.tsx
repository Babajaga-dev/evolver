"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import type { StrategySnapshotOut } from "@/lib/api";

interface Props {
  pareto: StrategySnapshotOut[];
  /** Tutte le strategy (sfondo grigio per contrasto). Optional. */
  background?: StrategySnapshotOut[];
  height?: number;
}

interface Point {
  sharpe: number;
  drawdown: number;
  generation: number;
  trades: number;
}

/**
 * Scatter 2D Sharpe robusto vs Max Drawdown |abs|.
 *
 * Front Pareto in oro grosso, sfondo (tutta la popolazione storica) in grigio
 * piccolo per dare la sensazione di "selezione" emergente.
 */
export function ParetoFront({ pareto, background = [], height = 320 }: Props) {
  const front = useMemo<Point[]>(
    () =>
      pareto.map((s) => ({
        sharpe: s.sharpe_robust,
        drawdown: s.max_drawdown_abs,
        generation: s.generation,
        trades: s.n_trades,
      })),
    [pareto],
  );

  const bg = useMemo<Point[]>(
    () =>
      background.map((s) => ({
        sharpe: s.sharpe_robust,
        drawdown: s.max_drawdown_abs,
        generation: s.generation,
        trades: s.n_trades,
      })),
    [background],
  );

  if (front.length === 0 && bg.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        Pareto front non ancora popolato.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 16 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--color-surface-border)" />
          <XAxis
            type="number"
            dataKey="drawdown"
            domain={["auto", "auto"]}
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            stroke="var(--color-surface-border)"
            label={{
              value: "max drawdown |abs|  (lower is better →)",
              position: "insideBottom",
              offset: -8,
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
            }}
          />
          <YAxis
            type="number"
            dataKey="sharpe"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => v.toFixed(2)}
            width={64}
            stroke="var(--color-surface-border)"
            label={{
              value: "sharpe robust  (↑ better)",
              angle: -90,
              position: "insideLeft",
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
            }}
          />
          <ZAxis range={[20, 70]} />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              borderRadius: 0,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
            labelStyle={{ color: "var(--color-gold)" }}
            cursor={{ strokeDasharray: "3 3" }}
            formatter={(value: number, name) => {
              if (name === "drawdown") return [`${(value * 100).toFixed(2)}%`, "max DD"];
              if (name === "sharpe") return [value.toFixed(3), "sharpe"];
              return [value, name];
            }}
          />
          {bg.length > 0 && (
            <Scatter
              name="population"
              data={bg}
              fill="var(--color-text-muted)"
              fillOpacity={0.25}
              shape="circle"
            />
          )}
          <Scatter
            name="pareto front"
            data={front}
            fill="var(--color-gold)"
            shape="circle"
            stroke="var(--color-btc)"
            strokeWidth={1}
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
