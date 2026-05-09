"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import type {
  GenerationSnapshotOut,
  StrategySnapshotOut,
} from "@/lib/api";

interface Props {
  generations: GenerationSnapshotOut[];
  strategies: StrategySnapshotOut[];
  status: string;
  maxLines?: number;
}

interface LogLine {
  ts: number;
  kind: "gen" | "best" | "warn" | "info" | "done";
  text: string;
}

/**
 * Stream terminal-style: per ogni generazione completata mostra
 * `[gen N] best Sharpe X.XX, mean Y.YY, diversity D` e
 * `[gen N] new best emerged: rsi_period=12, sharpe=0.74, trades=18`
 *
 * Aggiunge righe in coda con animazione fade-in. Auto-scroll all'ultima
 * a meno che l'utente non abbia scrollato manualmente in alto.
 */
export function EvolutionLog({
  generations,
  strategies,
  status,
  maxLines = 60,
}: Props) {
  const lines = useMemo<LogLine[]>(() => {
    const out: LogLine[] = [];
    out.push({
      ts: 0,
      kind: "info",
      text: `→ run starting · status=${status}`,
    });

    let bestSharpeSeen = -Infinity;
    let bestStrategy: StrategySnapshotOut | null = null;

    for (const g of generations) {
      out.push({
        ts: g.elapsed_seconds,
        kind: "gen",
        text:
          `[gen ${g.generation.toString().padStart(2, "0")}] ` +
          `best=${(-g.best_fitness).toFixed(3)} sharpe · ` +
          `mean=${(-g.mean_fitness).toFixed(3)} · ` +
          `diversity=${g.diversity.toFixed(3)} · ` +
          `dd=${(g.best_max_dd * 100).toFixed(1)}% · ` +
          `+${g.elapsed_seconds.toFixed(1)}s`,
      });

      // Trova il best individuo di questa generazione
      const inGen = strategies.filter((s) => s.generation === g.generation);
      if (inGen.length > 0) {
        const top = inGen.reduce((a, b) =>
          a.sharpe_robust > b.sharpe_robust ? a : b,
        );
        if (top.sharpe_robust > bestSharpeSeen) {
          bestSharpeSeen = top.sharpe_robust;
          bestStrategy = top;
          out.push({
            ts: g.elapsed_seconds,
            kind: "best",
            text:
              `★ new best emerged · ` +
              `sharpe=${top.sharpe_robust.toFixed(3)} · ` +
              `dd=${(top.max_drawdown_abs * 100).toFixed(1)}% · ` +
              `trades=${top.n_trades} · ` +
              chromosomeShort(top.chromosome),
          });
        }
      }

      // Convergence warning
      if (g.diversity < 0.05 && g.generation > 2) {
        out.push({
          ts: g.elapsed_seconds,
          kind: "warn",
          text: `! population converging fast (diversity=${g.diversity.toFixed(3)}). Possibile local optimum.`,
        });
      }
    }

    if (status === "completed") {
      out.push({
        ts: 0,
        kind: "done",
        text:
          `✓ evolution complete · best Sharpe ${bestSharpeSeen.toFixed(3)}` +
          (bestStrategy ? " · " + chromosomeShort(bestStrategy.chromosome) : ""),
      });
    } else if (status === "failed") {
      out.push({ ts: 0, kind: "warn", text: `✗ evolution failed` });
    } else if (status === "cancelled") {
      out.push({ ts: 0, kind: "warn", text: `◇ evolution cancelled by user` });
    }

    // Cap a maxLines (mantiene ultimi)
    return out.slice(-maxLines);
  }, [generations, strategies, status, maxLines]);

  return (
    <div
      className="max-h-[260px] overflow-y-auto border border-[--color-surface-border] bg-[--color-surface] p-3"
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        scrollbarColor: "var(--color-surface-border) var(--color-surface)",
      }}
    >
      <ol className="space-y-1">
        {lines.map((l, i) => (
          <li
            key={i}
            className="evolver-log-line"
            style={{
              color: colorFor(l.kind),
              animation: `evolverLogFadeIn 320ms ease-out`,
            }}
          >
            {l.text}
          </li>
        ))}
      </ol>
      <style jsx>{`
        @keyframes evolverLogFadeIn {
          from {
            opacity: 0;
            transform: translateX(-4px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @media (prefers-reduced-motion: reduce) {
          .evolver-log-line {
            animation: none !important;
          }
        }
      `}</style>
    </div>
  );
}

function colorFor(kind: LogLine["kind"]): string {
  switch (kind) {
    case "best":
      return "var(--color-gold)";
    case "done":
      return "var(--color-gold)";
    case "warn":
      return "var(--color-crimson)";
    case "gen":
      return "var(--color-text-secondary)";
    default:
      return "var(--color-text-muted)";
  }
}

function chromosomeShort(c: Record<string, number | string>): string {
  return Object.entries(c)
    .map(([k, v]) => {
      if (typeof v === "number") {
        return `${k}=${Number.isInteger(v) ? v : v.toFixed(2)}`;
      }
      return `${k}=${v}`;
    })
    .join(" ");
}
