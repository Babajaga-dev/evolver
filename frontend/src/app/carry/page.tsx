"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis, Area, AreaChart,
} from "recharts";

import { api, ApiError } from "@/lib/api";

interface CarryResp {
  symbol: string;
  start_date: string;
  end_date: string;
  n_funding_periods: number;
  n_trades: number;
  total_funding_collected: number;
  total_fees_paid: number;
  final_equity: number;
  total_return: number;
  sharpe: number;
  max_drawdown: number;
  win_rate: number;
  apr: number;
  equity_curve: Array<{ t: string; equity: number; in_position: boolean; funding_rate: number }>;
  trades: Array<{
    entry_time: string | null; exit_time: string | null;
    entry_price: number; exit_price: number | null;
    notional: number; funding_collected: number; n_funding_periods: number;
    fees_paid: number; pnl: number; pnl_pct: number;
  }>;
}

export default function CarryPage() {
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [startDate, setStartDate] = useState("2022-01-01");
  const [endDate, setEndDate] = useState("2022-12-31");
  const [timeframe, setTimeframe] = useState("4h");
  const [entryThr, setEntryThr] = useState(0.0001);
  const [exitThr, setExitThr] = useState(0.00005);
  const [positionFraction, setPositionFraction] = useState(0.5);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<CarryResp | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true); setError(null); setResult(null);
    try {
      const res = await fetch(
        (process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://api.evolve.lan") + "/api/v1/carry/run",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            start_date: new Date(startDate).toISOString(),
            end_date: new Date(endDate).toISOString(),
            timeframe,
            entry_threshold: entryThr,
            exit_threshold: exitThr,
            position_fraction: positionFraction,
          }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error((data && data.detail) || `HTTP ${res.status}`);
      setResult(data as CarryResp);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setRunning(false);
    }
  };

  return (
    <main
      style={{
        minHeight: "100svh",
        background: "var(--color-void)",
        color: "var(--color-warm-white)",
        padding: "var(--space-4)",
      }}
      className="md:px-12"
    >
      <header className="flex items-baseline justify-between">
        <div>
          <p
            className="text-[10px] uppercase tracking-[0.3em]"
            style={{ color: "var(--color-gold)", fontFamily: "var(--font-serif)" }}
          >
            · PHASE 7 · MARKET-NEUTRAL ALPHA ·
          </p>
          <h1
            style={{
              fontFamily: "var(--font-deco)",
              fontSize: "var(--fs-hero)",
              letterSpacing: ".05em",
              color: "var(--color-warm-white)",
            }}
          >
            CASH &amp; CARRY
          </h1>
          <p
            className="max-w-2xl text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-body)" }}
          >
            Funding rate arbitrage: long spot + short perpetual delta-neutral.
            Capture the funding payment senza esposizione direzionale. Sharpe
            documentato <strong>1.8</strong> (retail) / <strong>3.5</strong> (market
            maker) — He &amp; Manela 2024.
          </p>
        </div>
        <Link
          href="/"
          className="text-sm hover:underline"
          style={{ color: "var(--color-gold)", fontFamily: "var(--font-serif)", letterSpacing: ".2em" }}
        >
          ← HOME
        </Link>
      </header>

      <section
        className="mt-6 border bg-[--color-surface-card] p-4"
        style={{ borderColor: "var(--color-surface-border)" }}
      >
        <h2
          className="mb-3 text-[12px] uppercase tracking-[0.2em]"
          style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
        >
          Configurazione
        </h2>
        <div className="grid grid-cols-2 gap-3 text-xs md:grid-cols-4" style={{ fontFamily: "var(--font-mono)" }}>
          <Field label="Symbol">
            <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }}>
              <option value="BTC/USDT">BTC/USDT</option>
              <option value="ETH/USDT">ETH/USDT</option>
            </select>
          </Field>
          <Field label="Timeframe">
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }}>
              <option value="4h">4h</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
            </select>
          </Field>
          <Field label="Start"><input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }} /></Field>
          <Field label="End"><input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }} /></Field>
          <Field label="Entry threshold (per 8h)">
            <input type="number" step="0.00001" value={entryThr} onChange={(e) => setEntryThr(Number(e.target.value))} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }} />
          </Field>
          <Field label="Exit threshold (per 8h)">
            <input type="number" step="0.00001" value={exitThr} onChange={(e) => setExitThr(Number(e.target.value))} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }} />
          </Field>
          <Field label="Position fraction">
            <input type="number" step="0.1" min="0.1" max="1.0" value={positionFraction} onChange={(e) => setPositionFraction(Number(e.target.value))} className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]" style={{ border: "1px solid var(--color-surface-border)" }} />
          </Field>
          <div className="flex items-end">
            <button
              onClick={run}
              disabled={running}
              className="w-full py-2 text-xs uppercase tracking-[0.2em] disabled:opacity-50"
              style={{ background: "var(--color-btc-orange)", color: "var(--color-void)", fontFamily: "var(--font-serif)", fontWeight: 700 }}
            >
              {running ? "Backtesting..." : "◆ Run Carry"}
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div className="mt-3 border px-3 py-2 text-sm" style={{ borderColor: "var(--color-crimson)", fontFamily: "var(--font-mono)" }}>
          {error}
        </div>
      )}

      {result && (
        <>
          <section
            className="mt-6 border bg-[--color-surface-card] p-4"
            style={{ borderColor: "var(--color-gold)" }}
          >
            <p
              className="text-[10px] uppercase tracking-[0.25em]"
              style={{ color: "var(--color-gold)", fontFamily: "var(--font-serif)" }}
            >
              · BACKTEST RESULT ·
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
              <Metric label="Total return" value={`${(result.total_return * 100).toFixed(2)}%`} color={result.total_return >= 0 ? "#00ff99" : "var(--color-crimson)"} />
              <Metric label="APR" value={`${(result.apr * 100).toFixed(2)}%`} color={result.apr >= 0 ? "#00ff99" : "var(--color-crimson)"} />
              <Metric label="Sharpe" value={result.sharpe.toFixed(2)} color={result.sharpe >= 1 ? "var(--color-gold)" : "var(--color-text-primary)"} />
              <Metric label="Max DD" value={`${(result.max_drawdown * 100).toFixed(2)}%`} color="var(--color-crimson)" />
              <Metric label="N trades" value={String(result.n_trades)} />
              <Metric label="Win rate" value={`${(result.win_rate * 100).toFixed(0)}%`} />
              <Metric label="Funding collected" value={`$${result.total_funding_collected.toFixed(2)}`} color="var(--color-btc-orange)" />
              <Metric label="Fees paid" value={`$${result.total_fees_paid.toFixed(2)}`} color="var(--color-text-secondary)" />
            </div>
          </section>

          <section className="mt-4 border bg-[--color-surface-card] p-4" style={{ borderColor: "var(--color-surface-border)" }}>
            <h3 className="mb-2 text-[12px] uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}>
              Equity curve + funding rate
            </h3>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={result.equity_curve.map((p) => ({ t: new Date(p.t).getTime(), eq: p.equity, fr: p.funding_rate * 10000, pos: p.in_position ? 1 : 0 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-surface-border)" />
                <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)} stroke="var(--color-text-muted)" fontSize={10} />
                <YAxis yAxisId="left" stroke="var(--color-gold)" fontSize={10} />
                <YAxis yAxisId="right" orientation="right" stroke="var(--color-btc-orange)" fontSize={10} label={{ value: "funding bps", position: "insideRight", angle: 90, fill: "var(--color-text-muted)", fontSize: 9 }} />
                <Tooltip contentStyle={{ background: "var(--color-surface-card)", border: "1px solid var(--color-gold)", fontFamily: "var(--font-mono)", fontSize: 11 }} labelFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)} />
                <Legend wrapperStyle={{ fontFamily: "var(--font-serif)", fontSize: 11, letterSpacing: ".15em", textTransform: "uppercase" }} />
                <Line yAxisId="left" type="monotone" dataKey="eq" stroke="var(--color-gold)" strokeWidth={2} dot={false} name="Equity" />
                <Line yAxisId="right" type="monotone" dataKey="fr" stroke="var(--color-btc-orange)" strokeWidth={1.5} dot={false} name="Funding (bps)" />
              </LineChart>
            </ResponsiveContainer>
          </section>

          {result.trades.length > 0 && (
            <section className="mt-4 border bg-[--color-surface-card] overflow-x-auto" style={{ borderColor: "var(--color-surface-border)" }}>
              <h3 className="px-4 py-2 text-[12px] uppercase tracking-[0.2em]" style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}>
                Trades ({result.trades.length})
              </h3>
              <table className="w-full text-xs" style={{ fontFamily: "var(--font-mono)" }}>
                <thead>
                  <tr className="border-y border-[--color-surface-border] text-[10px] uppercase tracking-[0.2em] text-[--color-gold]" style={{ fontFamily: "var(--font-serif)" }}>
                    <th className="px-3 py-2 text-left">Entry</th>
                    <th className="px-3 py-2 text-left">Exit</th>
                    <th className="px-3 py-2 text-right">Notional</th>
                    <th className="px-3 py-2 text-right">Funding</th>
                    <th className="px-3 py-2 text-right">Fees</th>
                    <th className="px-3 py-2 text-right">P&amp;L</th>
                    <th className="px-3 py-2 text-right">P&amp;L %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-[--color-surface-border]/40">
                      <td className="px-3 py-1.5 text-[--color-text-primary]">{t.entry_time ? t.entry_time.slice(0, 10) : "—"}</td>
                      <td className="px-3 py-1.5 text-[--color-text-secondary]">{t.exit_time ? t.exit_time.slice(0, 10) : "—"}</td>
                      <td className="px-3 py-1.5 text-right text-[--color-text-secondary]">${t.notional.toFixed(0)}</td>
                      <td className="px-3 py-1.5 text-right" style={{ color: "var(--color-btc-orange)" }}>${t.funding_collected.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-[--color-text-secondary]">${t.fees_paid.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right" style={{ color: t.pnl >= 0 ? "#00ff99" : "var(--color-crimson)", fontWeight: 700 }}>${t.pnl.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right" style={{ color: t.pnl_pct >= 0 ? "#00ff99" : "var(--color-crimson)" }}>{(t.pnl_pct * 100).toFixed(2)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </>
      )}
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase tracking-[0.2em]" style={{ color: "var(--color-text-secondary)", fontFamily: "var(--font-serif)" }}>{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="border bg-[--color-surface-elevated] px-3 py-2" style={{ borderColor: "var(--color-surface-border)" }}>
      <p className="text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]" style={{ fontFamily: "var(--font-serif)" }}>{label}</p>
      <p style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700, color: color || "var(--color-text-primary)" }}>{value}</p>
    </div>
  );
}
