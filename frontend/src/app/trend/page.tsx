"use client";

/**
 * /trend — Donchian Ensemble Multi-Asset Trend Following
 *
 * Visual completo per spiegare l'evoluzione strategia:
 * - Form configurazione (simboli, periodo, parametri)
 * - 4 summary cards (Sharpe, Return, MaxDD, n_trades)
 * - Equity curve + buy-hold baseline overlay
 * - Exposure pct nel tempo (quanto investito)
 * - Monthly returns heatmap
 * - Per-asset breakdown table
 * - Trades table (ultimi 30)
 *
 * Paper ref: AdaptiveTrend arXiv 2602.11708 (Feb 2026) — Sharpe 2.41 OOS 2022-2024.
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
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, type TrendResponse } from "@/lib/api";

const DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT"];

export default function TrendPage() {
  const [result, setResult] = useState<TrendResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [symbolsStr, setSymbolsStr] = useState(DEFAULT_SYMBOLS.join(","));
  const [timeframe, setTimeframe] = useState("4h");
  const [startDate, setStartDate] = useState("2022-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [topN, setTopN] = useState(2);
  const [longWeight, setLongWeight] = useState(0.70);
  const [shortWeight, setShortWeight] = useState(0.30);
  const [targetVol, setTargetVol] = useState(0.40);
  const [trailingStopAtr, setTrailingStopAtr] = useState(3.0);
  const [rebalDays, setRebalDays] = useState(30);

  async function runBacktest() {
    try {
      setRunning(true);
      setError(null);
      const r = await api.trendRun({
        symbols: symbolsStr.split(",").map((s) => s.trim()).filter(Boolean),
        timeframe,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        top_n_assets: topN,
        long_weight: longWeight,
        short_weight: shortWeight,
        target_vol_annual: targetVol,
        trailing_stop_atr_mult: trailingStopAtr,
        rebalance_days: rebalDays,
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore backtest TREND");
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-[var(--gold)]/30 pb-4">
          <h1 className="text-3xl font-bold tracking-wider text-[var(--gold)] uppercase">
            Trend · Donchian Ensemble
          </h1>
          <p className="text-sm text-[var(--foreground)]/60 mt-1">
            Multi-lookback breakout + vol-targeting + trailing stop ATR + 70/30 long-short.
            Ref: AdaptiveTrend arXiv 2602.11708 (Sharpe 2.41 OOS 2022-2024).
          </p>
        </header>

        {/* Config form */}
        <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
          <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
            Configurazione backtest
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Field label="Symbols (csv)">
              <input
                type="text"
                value={symbolsStr}
                onChange={(e) => setSymbolsStr(e.target.value)}
                className="form-input"
              />
            </Field>
            <Field label="Timeframe">
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="form-input"
              >
                <option value="1h">1h</option>
                <option value="4h">4h</option>
                <option value="1d">1d</option>
              </select>
            </Field>
            <Field label="Start date">
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="form-input"
              />
            </Field>
            <Field label="End date">
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="form-input"
              />
            </Field>
            <Field label="Top N assets">
              <input
                type="number"
                min={1}
                max={20}
                value={topN}
                onChange={(e) => setTopN(parseInt(e.target.value) || 2)}
                className="form-input"
              />
            </Field>
            <Field label="Long weight">
              <input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={longWeight}
                onChange={(e) => setLongWeight(parseFloat(e.target.value) || 0.7)}
                className="form-input"
              />
            </Field>
            <Field label="Short weight">
              <input
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={shortWeight}
                onChange={(e) => setShortWeight(parseFloat(e.target.value) || 0.3)}
                className="form-input"
              />
            </Field>
            <Field label="Target vol annual">
              <input
                type="number"
                step="0.05"
                min={0.1}
                max={2.0}
                value={targetVol}
                onChange={(e) => setTargetVol(parseFloat(e.target.value) || 0.4)}
                className="form-input"
              />
            </Field>
            <Field label="Trailing stop (ATR x)">
              <input
                type="number"
                step="0.5"
                min={1}
                max={10}
                value={trailingStopAtr}
                onChange={(e) => setTrailingStopAtr(parseFloat(e.target.value) || 3)}
                className="form-input"
              />
            </Field>
            <Field label="Rebalance every (days)">
              <input
                type="number"
                min={1}
                max={365}
                value={rebalDays}
                onChange={(e) => setRebalDays(parseInt(e.target.value) || 30)}
                className="form-input"
              />
            </Field>
            <div className="col-span-2 flex items-end">
              <button
                type="button"
                onClick={runBacktest}
                disabled={running}
                className="w-full px-4 py-2 border-2 border-[var(--btc)] bg-[var(--btc)]/10 text-[var(--btc)] uppercase tracking-wider text-xs font-semibold hover:bg-[var(--btc)] hover:text-[var(--background)] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {running ? "Backtesting..." : "◆ Run TREND backtest"}
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
            {/* Summary cards */}
            <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <Card
                label="Sharpe"
                value={result.sharpe.toFixed(2)}
                hint={`Sortino ${result.sortino.toFixed(2)}`}
                color={result.sharpe >= 1 ? "#00FF99" : result.sharpe >= 0 ? "#C5A059" : "#8B1A1A"}
              />
              <Card
                label="Total return"
                value={`${(result.total_return * 100).toFixed(2)}%`}
                hint={`vs B&H ${(result.baselines.buy_hold_equal_weight.total_return * 100).toFixed(1)}%`}
                color={result.total_return >= 0 ? "#00FF99" : "#8B1A1A"}
              />
              <Card
                label="Max drawdown"
                value={`${(result.max_drawdown * 100).toFixed(2)}%`}
                hint={`vs B&H ${(result.baselines.buy_hold_equal_weight.max_drawdown * 100).toFixed(1)}%`}
                color={result.max_drawdown > -0.15 ? "#C5A059" : "#8B1A1A"}
              />
              <Card
                label="Trades"
                value={String(result.n_trades)}
                hint={`L ${result.n_long_trades} · S ${result.n_short_trades} · WR ${(result.win_rate * 100).toFixed(0)}%`}
              />
              <Card
                label="Alpha vs B&H"
                value={(result.sharpe - result.baselines.buy_hold_equal_weight.sharpe).toFixed(2)}
                hint="Sharpe diff"
                color={result.sharpe > result.baselines.buy_hold_equal_weight.sharpe ? "#00FF99" : "#8B1A1A"}
              />
            </section>

            {/* Equity curve */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Equity curve evolution
              </h2>
              <ResponsiveContainer width="100%" height={360}>
                <ComposedChart data={result.equity_curve.map((p) => ({
                  ...p,
                  exposure: p.exposure_pct * 100,
                }))}>
                  <defs>
                    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#C5A059" stopOpacity={0.55} />
                      <stop offset="100%" stopColor="#C5A059" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis
                    dataKey="t"
                    tick={{ fontSize: 11, fill: "#9898a8" }}
                    tickFormatter={(v) =>
                      new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })
                    }
                  />
                  <YAxis
                    yAxisId="eq"
                    tick={{ fontSize: 11, fill: "#9898a8" }}
                    domain={["auto", "auto"]}
                  />
                  <YAxis
                    yAxisId="exp"
                    orientation="right"
                    tick={{ fontSize: 11, fill: "#7799FF" }}
                    domain={[0, 100]}
                    label={{ value: "Exposure %", angle: 90, position: "insideRight", fill: "#7799FF", fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }}
                    labelFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT")}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area
                    yAxisId="eq"
                    type="monotone"
                    dataKey="equity"
                    name="TREND equity"
                    stroke="#C5A059"
                    strokeWidth={2}
                    fill="url(#eq)"
                    isAnimationActive={false}
                  />
                  <Line
                    yAxisId="exp"
                    type="monotone"
                    dataKey="exposure"
                    name="Exposure %"
                    stroke="#7799FF"
                    strokeWidth={1.2}
                    dot={false}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </section>

            {/* Monthly returns */}
            {result.monthly_returns.length > 0 && (
              <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                  Monthly returns
                </h2>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={result.monthly_returns}>
                    <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: "#9898a8" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#9898a8" }} unit="%" />
                    <Tooltip
                      contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }}
                      formatter={(v: number) => [`${v.toFixed(2)}%`, "Return"]}
                    />
                    <Bar dataKey="return_pct" name="Return %">
                      {result.monthly_returns.map((m, i) => (
                        <Cell key={i} fill={m.return_pct >= 0 ? "#6A8E3A" : "#8B1A1A"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </section>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Per-asset stats */}
              {result.per_asset_stats.length > 0 && (
                <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                  <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                    Per-asset performance
                  </h2>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-left text-[var(--foreground)]/60 border-b border-[var(--gold)]/20">
                        <th className="py-1.5 pr-2">Symbol</th>
                        <th className="py-1.5 pr-2 text-right">Trades</th>
                        <th className="py-1.5 pr-2 text-right">Wins</th>
                        <th className="py-1.5 pr-2 text-right">Tot PnL</th>
                        <th className="py-1.5 pr-2 text-right">Avg %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.per_asset_stats.map((a) => (
                        <tr key={a.symbol} className="border-b border-[var(--gold)]/10">
                          <td className="py-1 pr-2 font-mono text-[var(--gold)]">{a.symbol}</td>
                          <td className="py-1 pr-2 text-right">{a.n_trades}</td>
                          <td className="py-1 pr-2 text-right">{a.n_winners}</td>
                          <td className={`py-1 pr-2 text-right font-mono ${a.total_pnl >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>
                            {a.total_pnl.toFixed(2)}
                          </td>
                          <td className={`py-1 pr-2 text-right font-mono ${a.avg_pnl_pct >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>
                            {(a.avg_pnl_pct * 100).toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}

              {/* Recent trades */}
              {result.trades.length > 0 && (
                <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
                  <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                    Recent trades ({Math.min(result.trades.length, 20)} di {result.trades.length})
                  </h2>
                  <div className="overflow-y-auto max-h-[300px]">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-[var(--surface-card)]">
                        <tr className="text-left text-[var(--foreground)]/60 border-b border-[var(--gold)]/20">
                          <th className="py-1.5 pr-2">Symbol</th>
                          <th className="py-1.5 pr-2">Side</th>
                          <th className="py-1.5 pr-2">Exit</th>
                          <th className="py-1.5 pr-2 text-right">PnL%</th>
                          <th className="py-1.5 pr-2">Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.trades.slice(-20).reverse().map((t, i) => (
                          <tr key={i} className="border-b border-[var(--gold)]/10">
                            <td className="py-1 pr-2 font-mono text-[var(--gold)]">{t.symbol}</td>
                            <td className="py-1 pr-2 uppercase text-[10px]">
                              <span className={t.side === "long" ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}>
                                {t.side}
                              </span>
                            </td>
                            <td className="py-1 pr-2 font-mono">
                              {new Date(t.exit_time).toLocaleDateString("it-IT")}
                            </td>
                            <td className={`py-1 pr-2 text-right font-mono ${t.pnl_pct >= 0 ? "text-[#6A8E3A]" : "text-[#8B1A1A]"}`}>
                              {(t.pnl_pct * 100).toFixed(2)}%
                            </td>
                            <td className="py-1 pr-2 text-[10px] text-[var(--foreground)]/60">{t.reason}</td>
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
      <div className="text-[10px] uppercase tracking-widest text-[var(--foreground)]/50 mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

function Card({
  label,
  value,
  hint,
  color = "#C5A059",
}: {
  label: string;
  value: string;
  hint?: string;
  color?: string;
}) {
  return (
    <div className="border border-[var(--gold)]/30 bg-[var(--surface-card)] p-3 rounded">
      <div className="text-[10px] uppercase tracking-widest text-[var(--foreground)]/50">
        {label}
      </div>
      <div className="text-xl font-mono mt-1" style={{ color }}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-[var(--foreground)]/50 mt-1">{hint}</div>}
    </div>
  );
}
