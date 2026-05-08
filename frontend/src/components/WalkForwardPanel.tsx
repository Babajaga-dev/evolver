"use client";

import type {
  WalkForwardResponse,
  WalkForwardVerdict,
  WindowResult,
} from "@/lib/api";

interface Props {
  result: WalkForwardResponse;
}

const VERDICT_META: Record<
  WalkForwardVerdict,
  { label: string; color: string; symbol: string }
> = {
  robust: {
    label: "ROBUST",
    color: "var(--color-gold)",
    symbol: "✓",
  },
  mixed: {
    label: "MIXED",
    color: "var(--color-spd)", // gold electric
    symbol: "◆",
  },
  unstable: {
    label: "UNSTABLE",
    color: "var(--color-crimson)",
    symbol: "✕",
  },
  no_signal: {
    label: "NO SIGNAL",
    color: "var(--color-text-muted)",
    symbol: "◇",
  },
};

export function WalkForwardPanel({ result }: Props) {
  const s = result.summary;
  const meta = VERDICT_META[s.verdict];

  return (
    <div className="space-y-4">
      {/* Verdict card */}
      <div
        className="border-2 p-6"
        style={{
          borderColor: meta.color,
          backgroundColor: "var(--color-surface-card)",
        }}
      >
        <div className="mb-3 flex items-baseline gap-3">
          <span
            className="text-3xl"
            style={{ color: meta.color, fontFamily: "var(--font-deco)" }}
          >
            {meta.symbol}
          </span>
          <span
            className="text-2xl uppercase tracking-[0.4em]"
            style={{ color: meta.color, fontFamily: "var(--font-serif)" }}
          >
            {meta.label}
          </span>
          <span className="font-mono text-sm text-[--color-text-secondary]">
            · {s.n_windows_winning}/{s.n_windows} finestre vincenti
          </span>
        </div>
        <p className="font-mono text-xs text-[--color-text-secondary]">
          {s.verdict_reason}
        </p>
      </div>

      {/* Aggregate stats */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat
          label="Mean Return"
          value={pct(s.mean_total_return)}
          tone={s.mean_total_return >= 0 ? "good" : "bad"}
        />
        <Stat
          label="Std Return"
          value={pct(s.std_total_return)}
          tone="neutral"
        />
        <Stat
          label="Mean Sharpe"
          value={s.mean_sharpe !== null ? s.mean_sharpe.toFixed(2) : "—"}
          tone={
            s.mean_sharpe === null
              ? "neutral"
              : s.mean_sharpe >= 0.5
                ? "good"
                : s.mean_sharpe >= 0
                  ? "neutral"
                  : "bad"
          }
        />
        <Stat
          label="Worst MaxDD"
          value={pct(s.worst_max_drawdown)}
          tone={s.worst_max_drawdown > -0.2 ? "good" : "bad"}
        />
        <Stat
          label="Best Window"
          value={pct(s.best_total_return)}
          tone={s.best_total_return >= 0 ? "good" : "bad"}
        />
        <Stat
          label="Worst Window"
          value={pct(s.worst_total_return)}
          tone={s.worst_total_return >= 0 ? "good" : "bad"}
        />
        <Stat
          label="With Trades"
          value={`${s.n_windows_with_trades}/${s.n_windows}`}
          tone="neutral"
        />
        <Stat label="Mean MaxDD" value={pct(s.mean_max_drawdown)} tone="neutral" />
      </div>

      {/* Per-window table */}
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4">
        <h3
          className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          Windows · {result.windows.length}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full font-mono text-xs">
            <thead>
              <tr className="border-b border-[--color-surface-border] text-[--color-gold]">
                <Th>#</Th>
                <Th align="left">Period</Th>
                <Th>Trades</Th>
                <Th>Return</Th>
                <Th>Sharpe</Th>
                <Th>Max DD</Th>
                <Th>Win %</Th>
              </tr>
            </thead>
            <tbody>
              {result.windows.map((w) => (
                <WindowRow key={w.window_index} w={w} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "good" | "bad" | "neutral";
}) {
  const color =
    tone === "good"
      ? "var(--color-gold)"
      : tone === "bad"
        ? "var(--color-crimson)"
        : "var(--color-text-primary)";
  return (
    <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-3">
      <div
        className="mb-1 text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {label}
      </div>
      <div className="font-mono text-base" style={{ color }}>
        {value}
      </div>
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

function WindowRow({ w }: { w: WindowResult }) {
  const retColor =
    w.total_return >= 0 ? "var(--color-gold)" : "var(--color-crimson)";
  return (
    <tr className="border-b border-[--color-surface-border]/40">
      <td className="px-2 py-1.5 text-right text-[--color-gold]">
        {w.window_index + 1}
      </td>
      <td className="px-2 py-1.5 text-left text-[--color-text-secondary]">
        {fmtDate(w.window_start)} → {fmtDate(w.window_end)}
      </td>
      <td className="px-2 py-1.5 text-right">{w.n_trades}</td>
      <td className="px-2 py-1.5 text-right" style={{ color: retColor }}>
        {pct(w.total_return)}
      </td>
      <td className="px-2 py-1.5 text-right">
        {w.sharpe !== null && Number.isFinite(w.sharpe) ? w.sharpe.toFixed(2) : "—"}
      </td>
      <td className="px-2 py-1.5 text-right text-[--color-text-secondary]">
        {pct(w.max_drawdown)}
      </td>
      <td className="px-2 py-1.5 text-right text-[--color-text-secondary]">
        {w.win_rate !== null ? `${(w.win_rate * 100).toFixed(0)}%` : "—"}
      </td>
    </tr>
  );
}

function pct(v: number): string {
  return `${(v * 100).toFixed(2)}%`;
}

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}
