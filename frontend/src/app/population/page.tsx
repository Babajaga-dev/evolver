"use client";

import { useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DiversityChart } from "@/components/DiversityChart";
import { EvolutionLog } from "@/components/EvolutionLog";
import { SentimentBadge } from "@/components/SentimentBadge";
import { FitnessLandscape } from "@/components/FitnessLandscape";
import { ParameterHistograms } from "@/components/ParameterHistograms";
import { ParetoFront } from "@/components/ParetoFront";
import { PopulationCloud } from "@/components/PopulationCloud";
import { ProgressBar } from "@/components/ProgressBar";
import { StrategyLeaderboard } from "@/components/StrategyLeaderboard";
import {
  ApiError,
  api,
  type GaRunStatus,
  type MarketsResponse,
  type StrategyInfo,
} from "@/lib/api";

const PERIOD_OPTIONS = [
  { label: "180 giorni", days: 180 },
  { label: "1 anno", days: 365 },
  { label: "2 anni", days: 365 * 2 },
] as const;

export default function PopulationPage() {
  const [markets, setMarkets] = useState<MarketsResponse | null>(null);
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);

  const [strategyId, setStrategyId] = useState<string>("");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [timeframe, setTimeframe] = useState("4h");
  const [periodDays, setPeriodDays] = useState(365);
  const [populationSize, setPopulationSize] = useState(40);
  const [nGenerations, setNGenerations] = useState(15);
  const [nWindows, setNWindows] = useState(4);
  const [seed, setSeed] = useState(42);
  const [trainEndDaysAgo, setTrainEndDaysAgo] = useState(0);

  const [populationId, setPopulationId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<GaRunStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [cleanupOpen, setCleanupOpen] = useState(false);

  const pollerRef = useRef<NodeJS.Timeout | null>(null);

  const flashToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

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
          if (s.strategies.length > 0) setStrategyId(s.strategies[0].id);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiError ? `Init failed: ${e.message}` : "Init failed",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Polling 1Hz quando c'è un run attivo
  useEffect(() => {
    if (!populationId) return;

    const poll = async () => {
      try {
        const s = await api.getGaRun(populationId);
        setRunStatus(s);
        if (s.status === "completed" || s.status === "failed") {
          if (pollerRef.current) {
            clearInterval(pollerRef.current);
            pollerRef.current = null;
          }
        }
      } catch (e) {
        // 404: run scomparso (backend restartato, TTL Redis scaduto, ecc.).
        // Stoppa polling e mostra messaggio invece di flooding console.
        if (e instanceof ApiError && e.status === 404) {
          if (pollerRef.current) {
            clearInterval(pollerRef.current);
            pollerRef.current = null;
          }
          setError(
            `Run ${populationId} non più disponibile sul backend. ` +
              `Probabilmente il container è stato riavviato. Riavvia evolution.`,
          );
          setPopulationId(null);
          setRunStatus(null);
          return;
        }
        console.error("ga poll failed", e);
      }
    };

    poll(); // immediate first poll
    pollerRef.current = setInterval(poll, 1000);

    return () => {
      if (pollerRef.current) {
        clearInterval(pollerRef.current);
        pollerRef.current = null;
      }
    };
  }, [populationId]);

  const handleStart = async () => {
    if (!strategyId) return;
    setStarting(true);
    setError(null);
    setRunStatus(null);
    try {
      const created = await api.startGaRun({
        strategy_id: strategyId,
        symbol,
        timeframe,
        period_days: periodDays,
        initial_cash: 10_000,
        population_size: populationSize,
        n_generations: nGenerations,
        n_windows: nWindows,
        seed,
        train_end_days_ago: trainEndDaysAgo,
      });
      setPopulationId(created.population_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Start failed");
    } finally {
      setStarting(false);
    }
  };

  const isRunning =
    runStatus !== null &&
    (runStatus.status === "pending" || runStatus.status === "running");

  const progress =
    runStatus && runStatus.total_generations > 0
      ? runStatus.current_generation / runStatus.total_generations
      : 0;

  return (
    <main className="min-h-screen px-4 py-12 md:px-8 md:py-20">
      <div className="mx-auto max-w-6xl">
        <p className="mb-2 text-xs uppercase tracking-[0.4em] text-[--color-gold]">
          Evolver — Population
        </p>
        <h1
          className="mb-6 text-3xl md:text-5xl"
          style={{ fontFamily: "var(--font-deco)", letterSpacing: "0.08em" }}
        >
          Genetic Evolution
        </h1>
        <p className="mb-8 max-w-prose text-sm leading-relaxed text-[--color-text-secondary]">
          Una popolazione di cromosomi (parametri di una strategia) viene
          fatta evolvere con NSGA-II multi-obiettivo: massimizzare Sharpe
          robusto sulla walk-forward, minimizzare drawdown peggiore,
          mantenere semplicità. Ogni generazione la dashboard si aggiorna
          live.
        </p>

        {/* News regime context per l'asset selezionato — aggiornato 60s */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <span
            className="text-[10px] uppercase tracking-[0.3em]"
            style={{
              fontFamily: "var(--font-serif)",
              color: "var(--color-text-muted)",
            }}
          >
            News regime 24h:
          </span>
          <SentimentBadge asset={symbol.split("/")[0]} hours={24} compact />
        </div>

        {/* Form */}
        <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-6">
          <div className="grid gap-4 md:grid-cols-3">
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
            <Field label="Period">
              <select
                value={String(periodDays)}
                onChange={(e) => setPeriodDays(parseInt(e.target.value, 10))}
                className="select"
              >
                {PERIOD_OPTIONS.map((p) => (
                  <option key={p.days} value={p.days}>
                    {p.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Population size">
              <input
                type="number"
                min={10}
                max={200}
                value={populationSize}
                onChange={(e) => setPopulationSize(parseInt(e.target.value, 10))}
                className="input"
              />
            </Field>
            <Field label="N generations">
              <input
                type="number"
                min={2}
                max={200}
                value={nGenerations}
                onChange={(e) => setNGenerations(parseInt(e.target.value, 10))}
                className="input"
              />
            </Field>
            <Field label="Walk-forward windows">
              <input
                type="number"
                min={2}
                max={10}
                value={nWindows}
                onChange={(e) => setNWindows(parseInt(e.target.value, 10))}
                className="input"
              />
            </Field>
            <Field label="Seed">
              <input
                type="number"
                min={0}
                value={seed}
                onChange={(e) => setSeed(parseInt(e.target.value, 10))}
                className="input"
              />
            </Field>
            <Field label="Train ends N days ago">
              <input
                type="number"
                value={trainEndDaysAgo}
                onChange={(e) => setTrainEndDaysAgo(parseInt(e.target.value, 10))}
                min={0}
                max={1460}
                className="select"
              />
            </Field>
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              onClick={handleStart}
              disabled={starting || isRunning || !strategyId}
              className="border border-[--color-btc] bg-transparent px-6 py-2 font-mono text-sm uppercase tracking-[0.3em] text-[--color-btc] transition-colors hover:bg-[--color-surface-elevated] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {starting
                ? "◇ Starting…"
                : isRunning
                  ? "◇ Evolution in corso…"
                  : "◆ Start Evolution"}
            </button>
            {isRunning && populationId && (
              <button
                onClick={async () => {
                  if (!populationId) return;
                  try {
                    await api.stopGaRun(populationId);
                  } catch (e) {
                    console.error("stop failed", e);
                  }
                }}
                className="border border-[--color-crimson] bg-transparent px-4 py-2 font-mono text-xs uppercase tracking-[0.3em] text-[--color-crimson] transition-colors hover:bg-[--color-surface-elevated]"
              >
                ◇ Stop
              </button>
            )}
            <button
              onClick={() => setCleanupOpen(true)}
              className="border border-[--color-surface-border] bg-transparent px-4 py-2 font-mono text-xs uppercase tracking-[0.3em] text-[--color-text-muted] transition-colors hover:border-[--color-gold] hover:text-[--color-gold]"
            >
              ⌫ Cleanup
            </button>
            {error && (
              <span className="font-mono text-xs text-[--color-crimson]">
                ✕ {error}
              </span>
            )}
            {runStatus?.error && (
              <span className="font-mono text-xs text-[--color-crimson]">
                ✕ {runStatus.error}
              </span>
            )}
          </div>
        </section>

        {/* Progress header */}
        {runStatus && (
          <section
            className={`mb-6 border bg-[--color-surface-card] p-5 ${
              isRunning ? "evolver-pulse" : "border-[--color-surface-border]"
            }`}
            style={
              isRunning
                ? { borderColor: "var(--color-gold)" }
                : undefined
            }
          >
            <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2 font-mono text-xs">
              <div>
                <span
                  className="mr-3 uppercase tracking-[0.3em] text-[--color-gold]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {runStatus.status === "running"
                    ? "RUNNING"
                    : runStatus.status === "completed"
                      ? "COMPLETED"
                      : runStatus.status === "failed"
                        ? "FAILED"
                        : "PENDING"}
                </span>
                <span className="text-[--color-text-secondary]">
                  population <span className="text-[--color-gold]">{runStatus.population_id}</span>{" "}
                  · {runStatus.strategy_id} · {runStatus.symbol}{" "}
                  {runStatus.timeframe}
                </span>
              </div>
              <div className="text-[--color-text-secondary]">
                gen {runStatus.current_generation}/{runStatus.total_generations}
                {" · "}
                {formatElapsed(runStatus.elapsed_seconds)}
              </div>
            </div>
            <ProgressBar
              mode="determinate"
              value={progress}
              detail={`${(progress * 100).toFixed(0)}%`}
            />
          </section>
        )}

        {/* Evolution log: si vede subito come prima cosa quando il run parte */}
        {runStatus && (
          <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
            <h2
              className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Evolution Log
            </h2>
            <EvolutionLog
              generations={runStatus.generations}
              strategies={runStatus.top_strategies}
              status={runStatus.status}
            />
          </section>
        )}

        {/* Charts */}
        {runStatus && runStatus.generations.length > 0 && (
          <>
            {/* Population cloud — TUTTI gli individui */}
            <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Population Cloud · selezione naturale in atto
              </h2>
              <PopulationCloud
                strategies={runStatus.top_strategies}
                pareto={runStatus.pareto_front}
                currentGeneration={runStatus.current_generation}
              />
            </section>

            <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Fitness Landscape · Sharpe robusto
              </h2>
              <FitnessLandscape generations={runStatus.generations} />
            </section>

            <section className="mb-6 grid gap-4 md:grid-cols-2">
              <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4">
                <h2
                  className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  Pareto Front
                </h2>
                <ParetoFront
                  pareto={runStatus.pareto_front}
                  background={runStatus.top_strategies}
                />
              </div>
              <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4">
                <h2
                  className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  Diversity
                </h2>
                <DiversityChart generations={runStatus.generations} />
              </div>
            </section>

            {/* Parameter histograms — convergenza dei singoli params */}
            <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Parameter Convergence · distribuzione popolazione (top {runStatus.top_strategies.length})
              </h2>
              <ParameterHistograms strategies={runStatus.top_strategies} />
            </section>

            <section className="mb-16 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
              <h2
                className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Top Strategies · ranked by Sharpe robust
              </h2>
              <StrategyLeaderboard
                strategies={runStatus.top_strategies}
                maxRows={10}
              />
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
        <style jsx global>{`
          @keyframes evolverPulse {
            0%,
            100% {
              box-shadow: 0 0 0 0 rgba(197, 160, 89, 0);
            }
            50% {
              box-shadow: 0 0 18px 0 rgba(197, 160, 89, 0.45);
            }
          }
          .evolver-pulse {
            animation: evolverPulse 2.4s ease-in-out infinite;
            will-change: box-shadow;
          }
          @media (prefers-reduced-motion: reduce) {
            .evolver-pulse {
              animation: none;
            }
          }
        `}</style>
      </div>

      {/* Toast in-app (non blocca automation come l'alert nativo) */}
      {toast && (
        <div
          className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 border border-[--color-gold] bg-[--color-surface-card] px-4 py-2 text-sm text-[--color-gold]"
          style={{ fontFamily: "var(--font-mono)" }}
          role="status"
        >
          {toast}
        </div>
      )}

      <ConfirmDialog
        open={cleanupOpen}
        title="Cleanup runs"
        message="Cancellare tutti i run con status completed, failed o cancelled? I run in esecuzione restano intatti."
        confirmLabel="Conferma"
        cancelLabel="Annulla"
        destructive
        onCancel={() => setCleanupOpen(false)}
        onConfirm={async () => {
          setCleanupOpen(false);
          try {
            const r = await api.cleanupGaRuns();
            flashToast(`Eliminati ${r.deleted} run.`);
          } catch (e) {
            console.error("cleanup failed", e);
            setError(e instanceof Error ? e.message : "cleanup failed");
          }
        }}
      />
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

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}
