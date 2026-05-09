"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { GenerationSnapshotOut } from "@/lib/api";

interface Props {
  generations: GenerationSnapshotOut[];
  height?: number;
}

interface Point {
  generation: number;
  best: number;
  mean: number;
  worst: number;
}

/**
 * Line chart con best/mean/worst Sharpe robusto per generazione.
 *
 * Convertiamo la fitness pymoo (negativa per minimization) in Sharpe robusto
 * positivo (più alto = meglio) per leggibilità.
 */
export function FitnessLandscape({ generations, height = 280 }: Props) {
  const data = useMemo<Point[]>(
    () =>
      generations.map((g) => ({
        generation: g.generation,
        best: -g.best_fitness, // pymoo minimizza neg_sharpe → invertiamo
        mean: -g.mean_fitness,
        worst: -g.worst_fitness,
      })),
    [generations],
  );

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        Nessuna generazione completata. Lancia un run per iniziare.
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <CartesianGrid
            strokeDasharray="2 4"
            stroke="var(--color-surface-border)"
          />
          <XAxis
            dataKey="generation"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            stroke="var(--color-surface-border)"
            label={{
              value: "generation",
              position: "insideBottom",
              offset: -2,
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
            }}
          />
          <YAxis
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => v.toFixed(2)}
            width={64}
            stroke="var(--color-surface-border)"
            label={{
              value: "sharpe robust",
              angle: -90,
              position: "insideLeft",
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
            }}
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
            formatter={(value: number, name) => [value.toFixed(3), name]}
          />
          <Line
            type="monotone"
            dataKey="best"
            name="best"
            stroke="var(--color-gold)"
            strokeWidth={1.6}
            dot={{ r: 2 }}
            isAnimationActive={true}
            animationDuration={500}
          />
          <Line
            type="monotone"
            dataKey="mean"
            name="mean"
            stroke="var(--color-btc)"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={true}
            animationDuration={500}
          />
          <Line
            type="monotone"
            dataKey="worst"
            name="worst"
            stroke="var(--color-crimson)"
            strokeWidth={0.9}
            strokeDasharray="3 3"
            dot={false}
            isAnimationActive={true}
            animationDuration={500}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
