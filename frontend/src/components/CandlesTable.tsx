"use client";

import type { OHLCVCandle } from "@/lib/api";

interface Props {
  candles: OHLCVCandle[];
  maxRows?: number;
}

export function CandlesTable({ candles, maxRows = 20 }: Props) {
  if (candles.length === 0) {
    return (
      <p className="font-mono text-xs text-[--color-text-muted]">
        Empty range.
      </p>
    );
  }

  // Mostriamo le N più recenti — assumiamo input ordinato asc
  const tail = candles.slice(-maxRows).reverse();

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-[--color-surface-border] text-[--color-gold]">
            <th
              className="py-2 pr-4 text-left uppercase tracking-[0.2em]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Timestamp (UTC)
            </th>
            <th className="px-2 py-2 text-right uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)" }}>
              Open
            </th>
            <th className="px-2 py-2 text-right uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)" }}>
              High
            </th>
            <th className="px-2 py-2 text-right uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)" }}>
              Low
            </th>
            <th className="px-2 py-2 text-right uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)" }}>
              Close
            </th>
            <th className="py-2 pl-2 text-right uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)" }}>
              Volume
            </th>
          </tr>
        </thead>
        <tbody>
          {tail.map((c) => {
            const close = Number(c.close);
            const open = Number(c.open);
            const direction = close >= open ? "up" : "down";
            const dirColor =
              direction === "up"
                ? "var(--color-gold)"
                : "var(--color-crimson)";
            return (
              <tr
                key={c.timestamp}
                className="border-b border-[--color-surface-border]/40"
              >
                <td className="py-1.5 pr-4 text-[--color-text-secondary]">
                  {formatTs(c.timestamp)}
                </td>
                <td className="px-2 py-1.5 text-right">{fmt(c.open)}</td>
                <td className="px-2 py-1.5 text-right">{fmt(c.high)}</td>
                <td className="px-2 py-1.5 text-right">{fmt(c.low)}</td>
                <td
                  className="px-2 py-1.5 text-right"
                  style={{ color: dirColor }}
                >
                  {fmt(c.close)}
                </td>
                <td className="py-1.5 pl-2 text-right text-[--color-text-secondary]">
                  {Number(c.volume).toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function fmt(v: string): string {
  const n = Number(v);
  return n.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatTs(iso: string): string {
  const d = new Date(iso);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}
