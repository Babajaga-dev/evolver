"use client";

/**
 * /allocator — Risk Allocator (TREND + STAT-ARB + CARRY + F&G overlay)
 *
 * Visual che spiega evoluzione strategia multi-motore:
 * - Form configurazione (toggle engines, dates, overlays)
 * - 4 summary cards
 * - Stacked area chart: weights nel tempo (trend/statarb/carry)
 * - Equity curve combinata
 * - Per-engine metrics card grid
 * - Correlation matrix heatmap
 */

import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, type AllocatorResponse } from "@/lib/api";

const DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT"];

export default function AllocatorPage() {
  const [result, setResult] = useState<AllocatorResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [symbolsStr, setSymbolsStr] = useState(DEFAULT_SYMBOLS.join(","));
  const [timeframe, setTimeframe] = useState("4h");
  const [startDate, setStartDate] = useState("2023-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [rolling, setRolling] = useState(30);
  const [rebal, setRebal] = useState(7);
  const [applyFng, setApplyFng] = useState(true);
  const [runTrend, setRunTrend] = useState(true);
  const [runStatArb, setRunStatArb] = useState(true);
  const [runCarry, setRunCarry] = useState(true);

  async function runBacktest() {
    try {
      setRunning(true);
      setError(null);
      const r = await api.allocatorRun({
        symbols: symbolsStr.split(",").map((s) => s.trim()).filter(Boolean),
        timeframe,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        rolling_sharpe_days: rolling,
        rebalance_days: rebal,
        apply_fng_overlay: applyFng,
        run_trend: runTrend,
        run_statarb: runStatArb,
        run_carry: runCarry,
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore Allocator");
    } finally {
      setRunning(false);
    }
  }

  const ENGINE_COLORS: Record<string, string> = {
    trend: "#C5A059",
    statarb: "#7799FF",
    carry: "#F7931A",
  };

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-[var(--gold)]/30 pb-4">
          <h1 className="text-3xl font-bold tracking-wider text-[var(--gold)] uppercase">
            Allocator · Multi-Engine Risk Parity
          </h1>
          <p className="text-sm text-[var(--foreground)]/60 mt-1">
            TREND (Donchian ensemble) + STAT-ARB (cointegration) + CARRY (funding harvest),
            combinati con inverse-variance weights + F&G EMA-24w overlay.
            Ref: Topological Risk Parity arXiv 2604.16773 + paper-faithful engines.
          </p>
        </header>

        <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
          <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
            Configurazione
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Field label="Symbols (csv) for TREND">
              <input type="text" value={symbolsStr} onChange={(e) => setSymbolsStr(e.target.value)} className="form-input" />
            </Field>
            <Field label="Timeframe">
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="form-input">
                <option value="1h">1h</option>
                <option value="4h">4h</option>
                <option value="1d">1d</option>
              </select>
            </Field>
            <Field label="Start date">
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="form-input" />
            </Field>
            <Field label="End date">
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="form-input" />
            </Field>
            <Field label="Rolling Sharpe (days)">
              <input type="number" min={10} max={120} value={rolling} onChange={(e) => setRolling(parseInt(e.target.value) || 30)} className="form-input" />
            </Field>
            <Field label="Rebalance (days)">
              <input type="number" min={1} max={60} value={rebal} onChange={(e) => setRebal(parseInt(e.target.value) || 7)} className="form-input" />
            </Field>
            <Field label="Overlays">
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={applyFng} onChange={(e) => setApplyFng(e.target.checked)} />
                F&G EMA-24w
              </label>
            </Field>
            <Field label="Engines">
              <div className="flex flex-col gap-1 text-xs">
                <label><input type="checkbox" checked={runTrend} onChange={(e) => setRunTrend(e.target.checked)} /> TREND</label>
                <label><input type="checkbox" checked={runStatArb} onChange={(e) => setRunStatArb(e.target.checked)} /> STAT-ARB</label>
                <label><input type="checkbox" checked={runCarry} onChange={(e) => setRunCarry(e.target.checked)} /> CARRY</label>
              </div>
            </Field>
            <div className="col-span-2 flex items-end">
              <button
                type="button"
                onClick={runBacktest}
                disabled={running}
                className="w-full px-4 py-2 border-2 border-[var(--btc)] bg-[var(--btc)]/10 text-[var(--btc)] uppercase tracking-wider text-xs font-semibold hover:bg-[var(--btc)] hover:text-[var(--background)] disabled:opacity-40"
              >
                {running ? "Backtesting..." : "◆ Run ALLOCATOR"}
              </button>
            </div>
          </div>
        </section>

        {error && (
          <div className="p-4 border border-[#8B1A1A] bg-[#8B1A1A]/10 rounded text-[#FF6666] text-sm">
            {error}
          </div>
        )}

        {result && (
          <>
            <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card label="Sharpe" value={result.sharpe.toFixed(2)} hint={`Sortino ${result.sortino.toFixed(2)}`} color={result.sharpe >= 1 ? "#00FF99" : result.sharpe >= 0 ? "#C5A059" : "#8B1A1A"} />
              <Card label="Return" value={`${(result.total_return * 100).toFixed(2)}%`} hint={`Cash ${result.initial_cash.toFixed(0)} → ${result.final_equity.toFixed(0)}`} color={result.total_return >= 0 ? "#00FF99" : "#8B1A1A"} />
              <Card label="Max DD" value={`${(result.max_drawdown * 100).toFixed(2)}%`} color={result.max_drawdown > -0.15 ? "#C5A059" : "#8B1A1A"} />
              <Card label="Engines" value={result.config.engines_active.length.toString()} hint={result.config.engines_active.join(" + ").toUpperCase()} />
            </section>

            {/* Stacked area: weights over time */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Weight evolution · Engine allocation
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <AreaChart data={result.equity_curve.map((p) => ({
                  t: p.t,
                  trend: p.weight_trend * 100,
                  statarb: p.weight_statarb * 100,
                  carry: p.weight_carry * 100,
                }))}>
                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#9898a8" }} tickFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#9898a8" }} unit="%" />
                  <Tooltip contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }} labelFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT")} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="trend" stackId="1" stroke={ENGINE_COLORS.trend} fill={ENGINE_COLORS.trend} fillOpacity={0.5} isAnimationActive={false} />
                  <Area type="monotone" dataKey="statarb" stackId="1" stroke={ENGINE_COLORS.statarb} fill={ENGINE_COLORS.statarb} fillOpacity={0.5} isAnimationActive={false} />
                  <Area type="monotone" dataKey="carry" stackId="1" stroke={ENGINE_COLORS.carry} fill={ENGINE_COLORS.carry} fillOpacity={0.5} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </section>

            {/* Equity */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Combined equity curve
              </h2>
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={result.equity_curve}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#C5A059" stopOpacity={0.55} />
                      <stop offset="100%" stopColor="#C5A059" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#9898a8" }} tickFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })} />
                  <YAxis tick={{ fontSize: 11, fill: "#9898a8" }} domain={["auto", "auto"]} />
                  <Tooltip contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }} labelFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT")} />
                  <Area type="monotone" dataKey="equity" stroke="#C5A059" strokeWidth={2} fill="url(#eq)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </section>

            {/* Per-engine metrics + correlation */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                  Per-engine standalone metrics
                </h2>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[var(--foreground)]/60 border-b border-[var(--gold)]/20">
                      <th className="py-1.5 pr-2">Engine</th>
                      <th className="py-1.5 pr-2 text-right">Sharpe</th>
                      <th className="py-1.5 pr-2 text-right">Return</th>
                      <th className="py-1.5 pr-2 text-right">MaxDD</th>
                      <th className="py-1.5 pr-2 text-right">Trades</th>
                      <th className="py-1.5 pr-2 text-right">PnL Contrib</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.per_engine_metrics).map(([n, m]) => (
                      <tr key={n} className="border-b border-[var(--gold)]/10">
                        <td className="py-1.5 pr-2 font-mono uppercase" style={{ color: ENGINE_COLORS[n] }}>{n}</td>
                        <td className={`py-1.5 pr-2 text-right font-mono ${m.sharpe >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>{m.sharpe.toFixed(2)}</td>
                        <td className={`py-1.5 pr-2 text-right font-mono ${m.return >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>{(m.return * 100).toFixed(2)}%</td>
                        <td className="py-1.5 pr-2 text-right font-mono">{(m.max_drawdown * 100).toFixed(1)}%</td>
                        <td className="py-1.5 pr-2 text-right">{m.n_trades}</td>
                        <td className={`py-1.5 pr-2 text-right font-mono ${(result.per_engine_contribution[n] ?? 0) >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>
                          {(result.per_engine_contribution[n] ?? 0).toFixed(0)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>

              <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                  Correlation matrix
                </h2>
                <table className="w-full text-xs text-center">
                  <thead>
                    <tr>
                      <th></th>
                      {Object.keys(result.correlation_matrix).map((n) => (
                        <th key={n} className="py-1.5 text-[10px] uppercase" style={{ color: ENGINE_COLORS[n] }}>{n}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.correlation_matrix).map(([row, cols]) => (
                      <tr key={row}>
                        <th className="py-1.5 text-left text-[10px] uppercase" style={{ color: ENGINE_COLORS[row] }}>{row}</th>
                        {Object.entries(cols).map(([col, val]) => (
                          <td key={col} className="py-1.5 font-mono text-xs" style={{
                            color: val > 0.5 ? "#8B1A1A" : val > 0.2 ? "#C5A059" : val > -0.2 ? "#FFFFFF80" : "#6A8E3A",
                            background: `rgba(199,160,89,${Math.abs(val) * 0.15})`,
                          }}>
                            {val.toFixed(2)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-[var(--foreground)]/50 mt-2">
                  Verde = decorrelato (buona diversificazione). Rosso = correlato (overlap).
                </p>
              </section>
            </div>
          </>
        )}
      </div>

      <style jsx>{`
        :global(.form-input) {
          background: #1e1e2a;
          color: #e4e4ef;
          border: 1px solid #C5A059;
          padding: 6px 8px;
          font-size: 11px;
          width: 100%;
          color-scheme: dark;
        }
      `}</style>
    </main>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-[var(--foreground)]/50 mb-1">{label}</div>
      {children}
    </div>
  );
}

function Card({ label, value, hint, color = "#C5A059" }: { label: string; value: string; hint?: string; color?: string }) {
  return (
    <div className="border border-[var(--gold)]/30 bg-[var(--surface-card)] p-3 rounded">
      <div className="text-[10px] uppercase tracking-widest text-[var(--foreground)]/50">{label}</div>
      <div className="text-xl font-mono mt-1" style={{ color }}>{value}</div>
      {hint && <div className="text-[10px] text-[var(--foreground)]/50 mt-1">{hint}</div>}
    </div>
  );
}
