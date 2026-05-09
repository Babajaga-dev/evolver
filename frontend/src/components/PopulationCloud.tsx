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
  /** Tutti i cromosomi mai valutati (history). */
  strategies: StrategySnapshotOut[];
  /** Pareto front corrente (sottoinsieme — disegnato in oro). */
  pareto: StrategySnapshotOut[];
  /** Generazione corrente (per highlight individui ultimi). */
  currentGeneration: number;
  height?: number;
}

interface Point {
  drawdown: number;
  sharpe: number;
  generation: number;
  trades: number;
  ageBucket: number;
  size: number;
}

/**
 * "Cloud" 2D di tutti i cromosomi valutati nel run, segregati per età:
 *
 *   age=0  ultima generazione        → oro brillante (current frontier)
 *   age=1  generazione precedente    → btc orange (recent)
 *   age=2  due gen fa                → purple (epic tier)
 *   age=3  tre gen fa                → blue (rare tier)
 *   age=4+ vecchi                    → muted text (history)
 *
 * I punti del Pareto front sovrastano sopra come stelle bianche più grandi.
 * Animazione Recharts ON (300ms) → si vede selezione naturale che concentra
 * popolazione verso il bordo Pareto.
 */
export function PopulationCloud({
  strategies,
  pareto,
  currentGeneration,
  height = 360,
}: Props) {
  const buckets = useMemo(() => {
    // Buckets per età: 0=current, 1=prev, 2=2gen ago, 3=3+
    const result: { name: string; color: string; data: Point[] }[] = [
      { name: "history", color: "var(--color-text-muted)", data: [] },
      { name: "old (3+)", color: "#7799ff", data: [] }, // blue
      { name: "2 gen ago", color: "#bb77ff", data: [] }, // purple
      { name: "1 gen ago", color: "var(--color-btc)", data: [] }, // btc orange
      { name: "current gen", color: "var(--color-gold)", data: [] }, // gold
    ];

    for (const s of strategies) {
      const age = currentGeneration - s.generation;
      let bucketIdx: number;
      if (age <= 0) bucketIdx = 4;
      else if (age === 1) bucketIdx = 3;
      else if (age === 2) bucketIdx = 2;
      else if (age <= 4) bucketIdx = 1;
      else bucketIdx = 0;

      const sizeFromSharpe = Math.max(
        20,
        Math.min(120, 30 + s.sharpe_robust * 30),
      );

      result[bucketIdx].data.push({
        drawdown: s.max_drawdown_abs,
        sharpe: s.sharpe_robust,
        generation: s.generation,
        trades: s.n_trades,
        ageBucket: bucketIdx,
        size: sizeFromSharpe,
      });
    }

    return result;
  }, [strategies, currentGeneration]);

  const paretoPoints = useMemo<Point[]>(
    () =>
      pareto.map((s) => ({
        drawdown: s.max_drawdown_abs,
        sharpe: s.sharpe_robust,
        generation: s.generation,
        trades: s.n_trades,
        ageBucket: 99,
        size: 200,
      })),
    [pareto],
  );

  const totalPoints = strategies.length;

  if (totalPoints === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        Aspettando i primi cromosomi…
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height }}>
      <div
        className="mb-2 flex flex-wrap items-center gap-3 font-mono text-[10px] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <span>{totalPoints} individui</span>
        {buckets
          .slice()
          .reverse()
          .map((b) => (
            <span key={b.name} className="flex items-center gap-1.5">
              <span
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  background: b.color,
                  display: "inline-block",
                }}
              />
              {b.name}
            </span>
          ))}
        <span className="flex items-center gap-1.5">
          <span
            style={{
              width: 10,
              height: 10,
              border: "1px solid var(--color-warm-white)",
              background: "var(--color-warm-white)",
              display: "inline-block",
            }}
          />
          pareto front
        </span>
      </div>
      <ResponsiveContainer width="100%" height={height - 28}>
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
              value: "max drawdown |abs|  (lower better →)",
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
          <ZAxis dataKey="size" range={[20, 200]} />
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
              if (name === "generation") return [value, "gen"];
              if (name === "trades") return [value, "trades"];
              return [value, name];
            }}
          />
          {buckets.map((b) =>
            b.data.length === 0 ? null : (
              <Scatter
                key={b.name}
                name={b.name}
                data={b.data}
                fill={b.color}
                fillOpacity={b.name === "history" ? 0.18 : 0.55}
                isAnimationActive
                animationDuration={400}
              />
            ),
          )}
          {paretoPoints.length > 0 && (
            <Scatter
              name="pareto"
              data={paretoPoints}
              fill="var(--color-warm-white)"
              stroke="var(--color-gold)"
              strokeWidth={1.5}
              shape="cross"
              isAnimationActive
              animationDuration={500}
            />
          )}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
