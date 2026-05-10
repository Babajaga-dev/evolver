"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ApiError,
  api,
  type EquityCurveResponse,
  type PaperStateResponse,
  type PaperTradesResponse,
} from "@/lib/api";

export default function PaperPage() {
  const [state, setState] = useState<PaperStateResponse | null>(null);
  const [trades, setTrades] = useState<PaperTradesResponse | null>(null);
  const [equity, setEquity] = useState<EquityCurveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [s, t, e] = await Promise.all([
        api.paperState(),
        api.paperTrades(50),
        api.paperEquity(168, 500),
      ]);
      setState(s);
      setTrades(t);
      setEquity(e);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
    const interval = setInterval(reload, 30_000);
    return () => clearInterval(interval);
  }, [reload]);

  const flashToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const handleSnapshot = async () => {
    try {
      const r = await api.paperCreateSnapshot();
      flashToast(r.message);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Snapshot failed");
    }
  };

  return (
    <main className="min-h-screen px-4 py-8 md:px-8 md:py-12">
      <div className="mx-auto max-w-6xl">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p
              className="mb-1 text-xs uppercase tracking-[0.4em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Phase 4 · Paper Trading
            </p>
            <h1
              className="text-3xl md:text-5xl"
              style={{
                fontFamily: "var(--font-deco)",
                letterSpacing: "0.08em",
              }}
            >
              The Coin Vault
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[--color-text-secondary]">
              Simulazione di trading senza capitale reale. Posizioni, equity
              curve, statistiche di performance — esercizio del sistema prima
              di sfiorare denaro vero.
            </p>
          </div>
          <a
            href="/"
            className="text-xs uppercase tracking-[0.25em] text-[--color-text-secondary] hover:text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            ← Home
          </a>
        </div>

        {error && (
          <div
            className="mb-4 border border-[--color-crimson] bg-[--color-crimson]/10 px-4 py-2 text-sm"
            style={{ color: "var(--color-crimson, #e63946)" }}
          >
            {error}
          </div>
        )}
        {toast && (
          <div
            className="mb-4 border border-[--color-gold] bg-[--color-surface-card] px-4 py-2 text-sm text-[--color-gold]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {toast}
          </div>
        )}

        {loading ? (
          <p className="font-mono text-sm text-[--color-text-muted]">
            Caricando lo stato del portfolio...
          </p>
        ) : state ? (
          <>
            <StateCards state={state} />

            {state.status === "uninitialized" && (
              <section className="mb-8 border border-[--color-gold]/40 bg-[--color-surface-card] px-4 py-6 text-center">
                <p
                  className="text-[10px] uppercase tracking-[0.4em] text-[--color-gold]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  Portfolio non inizializzato
                </p>
                <p className="mt-2 text-sm text-[--color-text-secondary]">
                  Crea il primo snapshot di equity per cominciare il tracking.
                  Userà il balance iniziale dalle settings (
                  {new Intl.NumberFormat("en-US").format(state.initial_balance)}{" "}
                  USDT).
                </p>
                <button
                  type="button"
                  onClick={handleSnapshot}
                  className="mt-4 border border-[--color-gold] bg-[--color-gold]/10 px-4 py-2 text-xs uppercase tracking-[0.25em] text-[--color-gold] hover:bg-[--color-gold] hover:text-[--color-void]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  ◆ Inizializza portfolio
                </button>
              </section>
            )}

            <section className="mb-8">
              <h2
                className="mb-3 text-sm uppercase tracking-[0.3em] text-[--color-gold]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Equity Curve · 7 giorni
              </h2>
              <EquityChart equity={equity} initial={state.initial_balance} />
            </section>

            <section className="mb-8">
              <h2
                className="mb-3 text-sm uppercase tracking-[0.3em] text-[--color-gold]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Recent Trades
              </h2>
              <TradesTable trades={trades} />
            </section>
          </>
        ) : null}

        <footer
          className="mt-12 border-t border-[--color-surface-border] pt-4 text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          Auto-refresh ogni 30s · Slice 4.0a (read-only) · Engine generation in slice 4.0b.
        </footer>
      </div>
    </main>
  );
}

// ===========================================================================
// State cards
// ===========================================================================

function StateCards({ state }: { state: PaperStateResponse }) {
  const equityColor =
    state.total_return_pct > 0
      ? "var(--color-common, #00ff99)"
      : state.total_return_pct < 0
        ? "var(--color-crimson, #e63946)"
        : "var(--color-gold)";

  const cards = [
    {
      label: "Equity",
      value: `${formatNum(state.equity)} USDT`,
      tone: equityColor,
      sub: `Initial ${formatNum(state.initial_balance)}`,
    },
    {
      label: "Total return",
      value: `${state.total_return_pct >= 0 ? "+" : ""}${state.total_return_pct.toFixed(2)}%`,
      tone: equityColor,
      sub: `PnL: ${state.total_pnl >= 0 ? "+" : ""}${formatNum(state.total_pnl)}`,
    },
    {
      label: "Drawdown",
      value: `${(state.drawdown_from_peak * 100).toFixed(2)}%`,
      tone: "var(--color-crimson, #e63946)",
      sub: "from peak",
    },
    {
      label: "Open positions",
      value: String(state.open_positions_count),
      tone: "var(--color-gold)",
      sub: `${state.trades_total} total trades`,
    },
    {
      label: "Closed trades",
      value: String(state.trades_closed),
      tone: "var(--color-text-primary)",
      sub: `${state.trades_winning} winning`,
    },
    {
      label: "Win rate",
      value: state.trades_closed > 0
        ? `${(state.win_rate * 100).toFixed(1)}%`
        : "—",
      tone: state.win_rate > 0.5 ? "var(--color-common, #00ff99)" : "var(--color-text-primary)",
      sub: state.trades_closed > 0 ? `${state.trades_winning}/${state.trades_closed}` : "no closed yet",
    },
  ];

  return (
    <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 md:gap-4 lg:grid-cols-6">
      {cards.map((c) => (
        <div
          key={c.label}
          className="border border-[--color-surface-border] bg-[--color-surface-card] px-3 py-3"
        >
          <p
            className="text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            {c.label}
          </p>
          <p
            className="mt-1 text-lg md:text-xl"
            style={{
              fontFamily: "var(--font-mono)",
              color: c.tone,
              letterSpacing: "0.05em",
            }}
          >
            {c.value}
          </p>
          <p className="mt-1 text-[10px] text-[--color-text-muted]">{c.sub}</p>
        </div>
      ))}
    </div>
  );
}

// ===========================================================================
// Equity chart
// ===========================================================================

function EquityChart({
  equity,
  initial,
}: {
  equity: EquityCurveResponse | null;
  initial: number;
}) {
  if (!equity || equity.points.length === 0) {
    return (
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-8 text-center font-mono text-sm text-[--color-text-muted]">
        Nessun snapshot ancora. Crea il primo per disegnare la curve.
      </div>
    );
  }

  const data = equity.points.map((p) => ({
    timestamp: new Date(p.timestamp).getTime(),
    equity: p.equity,
    drawdown: -p.drawdown_from_peak * 100,
  }));

  return (
    <div
      className="border border-[--color-surface-border] bg-[--color-surface-card] p-4"
      style={{ height: 320 }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-gold)" stopOpacity={0.4} />
              <stop offset="100%" stopColor="var(--color-gold)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--color-surface-border)" strokeDasharray="2 4" />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            tick={{ fill: "var(--color-text-secondary)", fontFamily: "var(--font-mono)", fontSize: 10 }}
            stroke="var(--color-surface-border)"
          />
          <YAxis
            domain={[(dataMin: number) => Math.min(dataMin, initial * 0.98), "auto"]}
            tickFormatter={(v) => `${(v / 1000).toFixed(1)}k`}
            tick={{ fill: "var(--color-text-secondary)", fontFamily: "var(--font-mono)", fontSize: 10 }}
            stroke="var(--color-surface-border)"
            width={56}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              borderRadius: 0,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
            labelStyle={{ color: "var(--color-gold)" }}
            itemStyle={{ color: "var(--color-text-primary)" }}
            labelFormatter={(t) => new Date(Number(t)).toLocaleString()}
            formatter={(value: number) => [
              `${value.toFixed(2)} USDT`,
              "equity",
            ]}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke="var(--color-gold)"
            strokeWidth={1.6}
            fill="url(#equityFill)"
            isAnimationActive
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ===========================================================================
// Trades table
// ===========================================================================

function TradesTable({ trades }: { trades: PaperTradesResponse | null }) {
  if (!trades || trades.count === 0) {
    return (
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-8 text-center font-mono text-sm text-[--color-text-muted]">
        Nessun trade ancora. Quando il GA genererà segnali, i trade apparirranno qui.
      </div>
    );
  }

  return (
    <div
      className="border border-[--color-surface-border] bg-[--color-surface-card] overflow-x-auto"
      style={{ fontFamily: "var(--font-mono)" }}
    >
      <table className="w-full text-xs">
        <thead>
          <tr
            className="border-b border-[--color-surface-border] text-left text-[10px] uppercase tracking-[0.2em] text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            <th className="px-3 py-2">Entry</th>
            <th className="px-3 py-2">Symbol</th>
            <th className="px-3 py-2">Side</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Entry $</th>
            <th className="px-3 py-2 text-right">Exit $</th>
            <th className="px-3 py-2 text-right">PnL</th>
          </tr>
        </thead>
        <tbody>
          {trades.trades.map((t) => (
            <tr
              key={t.id}
              className="border-b border-[--color-surface-border]/40 text-[--color-text-secondary]"
            >
              <td className="px-3 py-2">
                {new Date(t.entry_time).toLocaleString()}
              </td>
              <td className="px-3 py-2 text-[--color-text-primary]">
                {t.symbol}
              </td>
              <td
                className="px-3 py-2"
                style={{
                  color:
                    t.side === "long"
                      ? "var(--color-common, #00ff99)"
                      : "var(--color-crimson, #e63946)",
                }}
              >
                {t.side}
              </td>
              <td className="px-3 py-2 text-[--color-text-muted]">{t.status}</td>
              <td className="px-3 py-2 text-right">{t.quantity.toFixed(6)}</td>
              <td className="px-3 py-2 text-right">{t.entry_price.toFixed(2)}</td>
              <td className="px-3 py-2 text-right">
                {t.exit_price !== null ? t.exit_price.toFixed(2) : "—"}
              </td>
              <td
                className="px-3 py-2 text-right"
                style={{
                  color:
                    t.pnl === null
                      ? "var(--color-text-muted)"
                      : t.pnl >= 0
                        ? "var(--color-common, #00ff99)"
                        : "var(--color-crimson, #e63946)",
                }}
              >
                {t.pnl !== null
                  ? `${t.pnl >= 0 ? "+" : ""}${t.pnl.toFixed(2)}`
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatNum(n: number): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(n);
}
