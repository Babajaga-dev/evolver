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

import type { GenerationSnapshotOut } from "@/lib/api";

interface Props {
  generations: GenerationSnapshotOut[];
  height?: number;
}

interface Point {
  generation: number;
  diversity: number;
}

/**
 * Diversity over generations.
 *
 * La diversità decresce naturalmente quando il GA converge. Una caduta
 * troppo rapida (verso 0) indica "premature convergence" — la popolazione
 * è collassata su un local optimum.
 */
export function DiversityChart({ generations, height = 200 }: Props) {
  const data = useMemo<Point[]>(
    () =>
      generations.map((g) => ({
        generation: g.generation,
        diversity: g.diversity,
      })),
    [generations],
  );

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        —
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <defs>
            <linearGradient id="diversityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-rare, #bb77ff)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--color-rare, #bb77ff)" stopOpacity={0.0} />
            </linearGradient>
          </defs>
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
          />
          <YAxis
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => v.toFixed(2)}
            width={56}
            stroke="var(--color-surface-border)"
            domain={[0, "auto"]}
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
            formatter={(value: number) => [value.toFixed(3), "diversity"]}
          />
          <Area
            type="monotone"
            dataKey="diversity"
            name="diversity"
            stroke="#bb77ff"
            strokeWidth={1.4}
            fill="url(#diversityFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
