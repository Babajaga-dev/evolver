"use client";

/**
 * /statarb — Statistical Arbitrage Pairs Trade (BTC/ETH cointegration)
 *
 * Visual che spiega evoluzione strategia market-neutral:
 * - Config form
 * - 5 summary cards (Sharpe, Return, MaxDD, Beta vs BTC, Cointegration p-value)
 * - Equity curve + Z-score evolution
 * - Spread chart con entry/exit markers
 * - Trades table
 *
 * Paper: IJSRA 2026-0283 Sharpe 1.58-2.45, beta 0.09-0.18, market-neutral.
 */

import { useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, type StatArbResponse } from "@/lib/api";

export default function StatArbPage() {
  const [result, setResult] = useState<StatArbResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [symA, setSymA] = useState("BTC/USDT");
  const [symB, setSymB] = useState("ETH/USDT");
  const [timeframe, setTimeframe] = useState("4h");
  const [startDate, setStartDate] = useState("2022-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [lookback, setLookback] = useState(180);
  const [zEntry, setZEntry] = useState(2.0);
  const [zExit, setZExit] = useState(0.5);
  const [zStop, setZStop] = useState(3.5);
  const [capPerTrade, setCapPerTrade] = useState(0.5);

  async function runBacktest() {
    try {
      setRunning(true);
      setError(null);
      const r = await api.statarbRun({
        symbol_a: symA,
        symbol_b: symB,
        timeframe,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        lookback_bars: lookback,
        z_entry: zEntry,
        z_exit: zExit,
        z_stop: zStop,
        capital_per_trade: capPerTrade,
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore StatArb");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-[var(--gold)]/30 pb-4">
          <h1 className="text-3xl font-bold tracking-wider text-[var(--gold)] uppercase">
            StatArb · Pairs Trade Cointegration
          </h1>
          <p className="text-sm text-[var(--foreground)]/60 mt-1">
            Pairs trade market-neutral su residual spread cointegrato. 
            Engle-Granger rolling + Z-score entry/exit + half-life filter.
            Ref: IJSRA 2026-0283 (Sharpe 1.58-2.45, beta 0.09-0.18).
          </p>
        </header>

        {/* Form */}
        <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
          <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
            Configurazione
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Field label="Symbol A">
              <input type="text" value={symA} onChange={(e) => setSymA(e.target.value)} className="form-input" />
            </Field>
            <Field label="Symbol B">
              <input type="text" value={symB} onChange={(e) => setSymB(e.target.value)} className="form-input" />
            </Field>
            <Field label="Timeframe">
              <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="form-input">
                <option value="1h">1h</option>
                <option value="4h">4h</option>
                <option value="1d">1d</option>
              </select>
            </Field>
            <Field label="Lookback bars">
              <input type="number" min={30} max={1000} value={lookback} onChange={(e) => setLookback(parseInt(e.target.value) || 180)} className="form-input" />
            </Field>
            <Field label="Start date">
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="form-input" />
            </Field>
            <Field label="End date">
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="form-input" />
            </Field>
            <Field label="Z entry">
              <input type="number" step="0.1" value={zEntry} onChange={(e) => setZEntry(parseFloat(e.target.value) || 2)} className="form-input" />
            </Field>
            <Field label="Z exit">
              <input type="number" step="0.1" value={zExit} onChange={(e) => setZExit(parseFloat(e.target.value) || 0.5)} className="form-input" />
            </Field>
            <Field label="Z stop">
              <input type="number" step="0.1" value={zStop} onChange={(e) => setZStop(parseFloat(e.target.value) || 3.5)} className="form-input" />
            </Field>
            <Field label="Capital per trade">
              <input type="number" step="0.05" min={0.1} max={1.0} value={capPerTrade} onChange={(e) => setCapPerTrade(parseFloat(e.target.value) || 0.5)} className="form-input" />
            </Field>
            <div className="col-span-2 flex items-end">
              <button
                type="button"
                onClick={runBacktest}
                disabled={running}
                className="w-full px-4 py-2 border-2 border-[var(--btc)] bg-[var(--btc)]/10 text-[var(--btc)] uppercase tracking-wider text-xs font-semibold hover:bg-[var(--btc)] hover:text-[var(--background)] disabled:opacity-40"
              >
                {running ? "Backtesting..." : "◆ Run STAT-ARB"}
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
            {/* Summary */}
            <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <Card label="Sharpe" value={result.sharpe.toFixed(2)} hint={`Sortino ${result.sortino.toFixed(2)}`} color={result.sharpe >= 1 ? "#00FF99" : result.sharpe >= 0 ? "#C5A059" : "#8B1A1A"} />
              <Card label="Return" value={`${(result.total_return * 100).toFixed(2)}%`} hint={`Win rate ${(result.win_rate * 100).toFixed(0)}%`} color={result.total_return >= 0 ? "#00FF99" : "#8B1A1A"} />
              <Card label="Max DD" value={`${(result.max_drawdown * 100).toFixed(2)}%`} hint={`${result.n_trades} trades`} color={result.max_drawdown > -0.15 ? "#C5A059" : "#8B1A1A"} />
              <Card label="Beta vs BTC" value={result.beta_vs_btc.toFixed(3)} hint="market-neutral target ~0" color={Math.abs(result.beta_vs_btc) < 0.3 ? "#00FF99" : "#C5A059"} />
              <Card label="Cointegration p" value={result.cointegration_p_value.toFixed(4)} hint={result.cointegration_p_value < 0.05 ? "✓ statistically significant" : "weak"} color={result.cointegration_p_value < 0.05 ? "#00FF99" : "#8B1A1A"} />
            </section>

            {/* Equity */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Equity curve · Strategy evolution
              </h2>
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={result.equity_curve}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#C5A059" stopOpacity={0.55} />
                      <stop offset="100%" stopColor="#C5A059" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#9898a8" }} tickFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })} />
                  <YAxis tick={{ fontSize: 11, fill: "#9898a8" }} />
                  <Tooltip contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }} labelFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT")} />
                  <Area type="monotone" dataKey="equity" stroke="#C5A059" strokeWidth={2} fill="url(#eq)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </section>

            {/* Z-score */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Spread Z-score · entry/exit thresholds
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={result.equity_curve.filter((_, i) => i % Math.max(1, Math.floor(result.equity_curve.length / 800)) === 0)}>
                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis dataKey="t" tick={{ fontSize: 11, fill: "#9898a8" }} tickFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })} />
                  <YAxis tick={{ fontSize: 11, fill: "#9898a8" }} domain={[-5, 5]} />
                  <ReferenceLine y={zEntry} stroke="#00FF99" strokeDasharray="3 3" strokeOpacity={0.7} label={{ value: `+entry ${zEntry}`, fill: "#00FF99", fontSize: 10, position: "right" }} />
                  <ReferenceLine y={-zEntry} stroke="#00FF99" strokeDasharray="3 3" strokeOpacity={0.7} label={{ value: `-entry ${-zEntry}`, fill: "#00FF99", fontSize: 10, position: "right" }} />
                  <ReferenceLine y={zExit} stroke="#C5A059" strokeDasharray="2 4" strokeOpacity={0.5} />
                  <ReferenceLine y={-zExit} stroke="#C5A059" strokeDasharray="2 4" strokeOpacity={0.5} />
                  <ReferenceLine y={zStop} stroke="#8B1A1A" strokeDasharray="3 3" strokeOpacity={0.7} label={{ value: `stop ${zStop}`, fill: "#8B1A1A", fontSize: 10, position: "right" }} />
                  <ReferenceLine y={-zStop} stroke="#8B1A1A" strokeDasharray="3 3" strokeOpacity={0.7} />
                  <Tooltip contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }} labelFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT")} />
                  <Line type="monotone" dataKey="zscore" stroke="#7799FF" strokeWidth={1.2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </section>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {result.monthly_returns.length > 0 && (
                <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                  <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                    Monthly returns
                  </h2>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={result.monthly_returns}>
                      <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                      <XAxis dataKey="month" tick={{ fontSize: 10, fill: "#9898a8" }} />
                      <YAxis tick={{ fontSize: 11, fill: "#9898a8" }} unit="%" />
                      <Tooltip contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }} formatter={(v: number) => [`${v.toFixed(2)}%`, "Return"]} />
                      <Bar dataKey="return_pct">
                        {result.monthly_returns.map((m, i) => (
                          <Cell key={i} fill={m.return_pct >= 0 ? "#6A8E3A" : "#8B1A1A"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </section>
              )}

              {result.trades.length > 0 && (
                <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                  <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                    Trades ({result.trades.length})
                  </h2>
                  <div className="overflow-y-auto max-h-[260px]">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-[var(--surface-card)]">
                        <tr className="text-left text-[var(--foreground)]/60 border-b border-[var(--gold)]/20">
                          <th className="py-1.5 pr-2">Exit</th>
                          <th className="py-1.5 pr-2">Side</th>
                          <th className="py-1.5 pr-2 text-right">Entry Z</th>
                          <th className="py-1.5 pr-2 text-right">Exit Z</th>
                          <th className="py-1.5 pr-2 text-right">PnL%</th>
                          <th className="py-1.5 pr-2">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.slice(-30).reverse().map((t, i) => (
                          <tr key={i} className="border-b border-[var(--gold)]/10">
                            <td className="py-1 pr-2 font-mono">{new Date(t.exit_time).toLocaleDateString("it-IT")}</td>
                            <td className={`py-1 pr-2 uppercase text-[10px] ${t.side === "long_spread" ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>{t.side.replace("_spread", "")}</td>
                            <td className="py-1 pr-2 text-right font-mono">{t.entry_z.toFixed(2)}</td>
                            <td className="py-1 pr-2 text-right font-mono">{t.exit_z.toFixed(2)}</td>
                            <td className={`py-1 pr-2 text-right font-mono ${t.pnl_pct >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>{(t.pnl_pct * 100).toFixed(2)}%</td>
                            <td className="py-1 pr-2 text-[10px]">{t.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
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
