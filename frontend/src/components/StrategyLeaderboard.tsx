"use client";

import type { StrategySnapshotOut } from "@/lib/api";

interface Props {
  strategies: StrategySnapshotOut[];
  maxRows?: number;
}

export function StrategyLeaderboard({ strategies, maxRows = 10 }: Props) {
  if (strategies.length === 0) {
    return (
      <p className="font-mono text-xs text-[--color-text-muted]">
        Leaderboard vuota — il GA sta ancora valutando i primi cromosomi.
      </p>
    );
  }

  const top = strategies.slice(0, maxRows);

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-[--color-surface-border] text-[--color-gold]">
            <Th align="left">#</Th>
            <Th>Sharpe (rob)</Th>
            <Th>Max DD</Th>
            <Th>Trades</Th>
            <Th>Win wins</Th>
            <Th>Gen</Th>
            <Th align="left">Chromosome</Th>
          </tr>
        </thead>
        <tbody>
          {top.map((s, i) => {
            const sharpeColor =
              s.sharpe_robust >= 0.5
                ? "var(--color-gold)"
                : s.sharpe_robust >= 0
                  ? "var(--color-text-primary)"
                  : "var(--color-crimson)";
            return (
              <tr
                key={`${s.generation}_${i}_${JSON.stringify(s.chromosome)}`}
                className="border-b border-[--color-surface-border]/40"
              >
                <td className="py-1.5 pl-2 pr-3 text-left text-[--color-gold]">
                  {i + 1}
                </td>
                <td
                  className="px-2 py-1.5 text-right"
                  style={{ color: sharpeColor }}
                >
                  {s.sharpe_robust.toFixed(3)}
                </td>
                <td className="px-2 py-1.5 text-right text-[--color-text-secondary]">
                  {(s.max_drawdown_abs * 100).toFixed(2)}%
                </td>
                <td className="px-2 py-1.5 text-right text-[--color-text-secondary]">
                  {s.n_trades}
                </td>
                <td className="px-2 py-1.5 text-right text-[--color-text-secondary]">
                  {s.n_windows_winning}
                </td>
                <td className="px-2 py-1.5 text-right text-[--color-text-muted]">
                  {s.generation}
                </td>
                <td className="px-2 py-1.5 text-left text-[--color-text-secondary]">
                  {formatChromosome(s.chromosome)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "right",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      className={`py-2 px-2 ${align === "left" ? "text-left" : "text-right"} uppercase tracking-[0.2em]`}
      style={{ fontFamily: "var(--font-serif)" }}
    >
      {children}
    </th>
  );
}

function formatChromosome(c: Record<string, number | string>): string {
  return Object.entries(c)
    .map(([k, v]) => {
      if (typeof v === "number") {
        return `${k}=${Number.isInteger(v) ? v : v.toFixed(2)}`;
      }
      return `${k}=${v}`;
    })
    .join(", ");
}
