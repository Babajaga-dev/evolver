"use client";

import { useEffect, useState } from "react";

import { EquityCurve } from "@/components/EquityCurve";
import { MetricCards } from "@/components/MetricCards";
import { TradesTable } from "@/components/TradesTable";
import {
  ApiError,
  api,
  type BacktestResponse,
  type MarketsResponse,
  type StrategyInfo,
} from "@/lib/api";

const PERIODS = [
  { label: "90 giorni", days: 90 },
  { label: "180 giorni", days: 180 },
  { label: "1 anno", days: 365 },
  { label: "2 anni", days: 365 * 2 },
  { label: "5 anni", days: 365 * 5 },
] as const;

type PeriodOption = (typeof PERIODS)[number];

export default function BacktestPage() {
  const [markets, setMarkets] = useState<MarketsResponse | null>(null);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);

  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("4h");
  const [strategyId, setStrategyId] = useState<string>("");
  const [period, setPeriod] = useState<PeriodOption>(PERIODS[2]);
  const [initialCash, setInitialCash] = useState(10_000);

  const [paramValues, setParamValues] = useState<Record<string, string>>({});

  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Mount: markets + strategies
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [m, s] = await Promise.all([
          api.markets(),
          api.strategiesRegistry(),
        ]);
        if (!cancelled) {
          setMarkets(m);
          setStrategies(s.strategies);
          if (s.strategies.length > 0) {
            const first = s.strategies[0];
            setStrategyId(first.id);
            setParamValues(
              Object.fromEntries(
                first.params.map((p) => [p.name, String(p.default)]),
              ),
            );
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiError
              ? `Init failed: ${e.message}`
              : "Init failed",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Quando cambia strategy_id reimposta i param values dai default
  useEffect(() => {
    const spec = strategies.find((s) => s.id === strategyId);
    if (!spec) return;
    setParamValues(
      Object.fromEntries(spec.params.map((p) => [p.name, String(p.default)])),
    );
  }, [strategyId, strategies]);

  const currentStrategy = strategies.find((s) => s.id === strategyId);

  const handleRun = async () => {
    if (!currentStrategy) return;
    setRunning(true);
    setError(null);
    setResult(null);

    // Cast params al tipo corretto
    const parsedParams: Record<string, number | string> = {};
    for (const p of currentStrategy.params) {
      const raw = paramValues[p.name];
      if (raw === undefined) continue;
      parsedParams[p.name] =
        p.type === "int"
          ? parseInt(raw, 10)
          : p.type === "float"
            ? parseFloat(raw)
            : raw;
    }

    try {
      const res = await api.runBacktest({
        symbol,
        timeframe,
        strategy_id: strategyId,
        params: parsedParams,
        period_days: period.days,
        initial_cash: initialCash,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="min-h-screen px-4 py-12 md:px-8 md:py-20">
      <div className="mx-auto max-w-6xl">
        <p className="mb-2 text-xs uppercase tracking-[0.4em] text-[--color-gold]">
          Evolver — Backtest Engine
        </p>
        <h1
          className="mb-6 text-3xl md:text-5xl"
          style={{ fontFamily: "var(--font-deco)", letterSpacing: "0.08em" }}
        >
          Backtest
        </h1>
        <p className="mb-8 max-w-prose text-sm leading-relaxed text-[--color-text-secondary]">
          Simulazione vectorized (vectorbt) di una strategia preset su dati
          storici reali. Fee taker Binance 0.10% + slippage 2 bps inclusi nel
          calcolo. Ogni metrica è risk-adjusted.
        </p>

        {/* Form */}
        <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-6">
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Symbol">
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                className="select"
              >
                {(markets?.symbols ?? [symbol]).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Timeframe">
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="select"
              >
                {(markets?.timeframes ?? [timeframe]).map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Strategy">
              <select
                value={strategyId}
                onChange={(e) => setStrategyId(e.target.value)}
                className="select"
              >
                {strategies.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Period">
              <select
                value={String(period.days)}
                onChange={(e) =>
                  setPeriod(
                    PERIODS.find((p) => String(p.days) === e.target.value) ??
                      PERIODS[2],
                  )
                }
                className="select"
              >
                {PERIODS.map((p) => (
                  <option key={p.days} value={p.days}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Initial cash (USDT)">
              <input
                type="number"
                value={initialCash}
                onChange={(e) => setInitialCash(parseInt(e.target.value, 10))}
                className="input"
                min={100}
                step={100}
              />
            </Field>
          </div>

          {currentStrategy && (
            <div className="mt-4 border-t border-[--color-surface-border] pt-4">
              <h3
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Strategy Parameters
              </h3>
              <p className="mb-4 text-xs text-[--color-text-secondary]">
                {currentStrategy.description}
              </p>
              <div className="grid gap-3 md:grid-cols-3">
                {currentStrategy.params.map((p) => (
                  <Field key={p.name} label={p.name}>
                    <input
                      type="number"
                      step={p.type === "float" ? "0.1" : "1"}
                      min={p.min ?? undefined}
                      max={p.max ?? undefined}
                      value={paramValues[p.name] ?? ""}
                      onChange={(e) =>
                        setParamValues((v) => ({
                          ...v,
                          [p.name]: e.target.value,
                        }))
                      }
                      className="input"
                    />
                    {p.min !== null && p.min !== undefined && (
                      <span className="mt-1 block font-mono text-[10px] text-[--color-text-muted]">
                        [{p.min} – {p.max}]
                      </span>
                    )}
                  </Field>
                ))}
              </div>
            </div>
          )}

          <div className="mt-6 flex items-center gap-4">
            <button
              onClick={handleRun}
              disabled={running || !currentStrategy}
              className="border border-[--color-btc] bg-transparent px-6 py-2 font-mono text-sm uppercase tracking-[0.3em] text-[--color-btc] transition-colors hover:bg-[--color-surface-elevated] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? "◇ Running…" : "◆ Run Backtest"}
            </button>
            {error && (
              <span className="font-mono text-xs text-[--color-crimson]">
                ✕ {error}
              </span>
            )}
          </div>
        </section>

        {/* Results */}
        {result && (
          <>
            <section className="mb-6">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Metrics ·{" "}
                <span className="text-[--color-gold]">
                  {result.strategy_label}
                </span>{" "}
                · {result.symbol} {result.timeframe} · {paramsCompact(result.params)}
              </h2>
              <MetricCards metrics={result.metrics} />
            </section>

            <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Equity Curve
              </h2>
              <EquityCurve
                points={result.equity_curve}
                initialCash={result.initial_cash}
              />
            </section>

            <section className="mb-16 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Trades · {result.trades.length} totali
              </h2>
              <TradesTable trades={result.trades} maxRows={50} />
            </section>
          </>
        )}

        <footer className="mt-12 text-xs text-[--color-text-muted]">
          <a
            href="/"
            className="hover:text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            ← Back to home
          </a>
        </footer>

        <style jsx>{`
          .select,
          .input {
            width: 100%;
            border: 1px solid var(--color-surface-border);
            background: var(--color-surface);
            padding: 0.5rem 0.75rem;
            font-family: var(--font-mono);
            font-size: 0.875rem;
            color: var(--color-text-primary);
            border-radius: 0;
          }
          .select:focus,
          .input:focus {
            outline: none;
            border-color: var(--color-gold);
          }
        `}</style>
      </div>
    </main>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span
        className="mb-1.5 block text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

function paramsCompact(params: Record<string, number | string>): string {
  return Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
}
