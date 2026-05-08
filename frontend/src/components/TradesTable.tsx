"use client";

import type { TradeRecord } from "@/lib/api";

interface Props {
  trades: TradeRecord[];
  maxRows?: number;
}

export function TradesTable({ trades, maxRows = 30 }: Props) {
  if (trades.length === 0) {
    return (
      <p className="font-mono text-xs text-[--color-text-muted]">
        Nessun trade eseguito (controlla parametri strategia o range).
      </p>
    );
  }

  // Most recent first
  const sorted = [...trades]
    .sort(
      (a, b) =>
        new Date(b.entry_time).getTime() - new Date(a.entry_time).getTime(),
    )
    .slice(0, maxRows);

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-[--color-surface-border] text-[--color-gold]">
            <th
              className="py-2 pr-3 text-left uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Entry
            </th>
            <th
              className="py-2 pr-3 text-left uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Exit
            </th>
            <th
              className="py-2 pr-3 text-right uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Entry $
            </th>
            <th
              className="py-2 pr-3 text-right uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Exit $
            </th>
            <th
              className="py-2 pr-3 text-right uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              PnL
            </th>
            <th
              className="py-2 pr-3 text-right uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              PnL %
            </th>
            <th
              className="py-2 text-left uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Side
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((t, i) => {
            const pnlColor =
              t.pnl >= 0 ? "var(--color-gold)" : "var(--color-crimson)";
            return (
              <tr
                key={`${t.entry_time}_${i}`}
                className="border-b border-[--color-surface-border]/40"
              >
                <td className="py-1.5 pr-3 text-[--color-text-secondary]">
                  {fmtTs(t.entry_time)}
                </td>
                <td className="py-1.5 pr-3 text-[--color-text-secondary]">
                  {t.exit_time ? fmtTs(t.exit_time) : "open"}
                </td>
                <td className="py-1.5 pr-3 text-right">
                  {t.entry_price.toFixed(2)}
                </td>
                <td className="py-1.5 pr-3 text-right">
                  {t.exit_price !== null ? t.exit_price.toFixed(2) : "—"}
                </td>
                <td
                  className="py-1.5 pr-3 text-right"
                  style={{ color: pnlColor }}
                >
                  {t.pnl.toFixed(2)}
                </td>
                <td
                  className="py-1.5 pr-3 text-right"
                  style={{ color: pnlColor }}
                >
                  {(t.pnl_pct * 100).toFixed(2)}%
                </td>
                <td
                  className="py-1.5 text-[--color-text-secondary]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {t.direction}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function fmtTs(iso: string): string {
  const d = new Date(iso);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}
