"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
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

import {
  api,
  type ReplayDetailResponse,
  type ReplayEquityPoint,
  type ReplayRetrainEvent,
  type ReplayRunSummary,
  type ReplayStartParams,
} from "@/lib/api";

const VERDICT_COLORS: Record<string, string> = {
  pending: "var(--color-text-secondary)",
  running: "var(--color-btc-orange)",
  stopping: "var(--color-crimson)",
  cancelled: "var(--color-text-muted)",
  failed: "var(--color-crimson)",
  completed: "var(--color-gold)",
};

const REGIME_COLORS: Record<string, string> = {
  trend_bullish: "#00ff99",
  trend_bearish: "#e63946",
  trend_mixed: "#f4a261",
  range_low_vol: "#7799ff",
  range_high_vol: "#bb77ff",
  range: "#9898a8",
  transition: "#5a5a6a",
};

export default function ReplayPage() {
  const [runs, setRuns] = useState<ReplayRunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReplayDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchList = useCallback(async () => {
    try {
      const r = await api.replayList();
      setRuns(r.runs);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  const fetchDetail = useCallback(async (id: string) => {
    try {
      const r = await api.replayDetail(id, 5000);
      setDetail(r);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    fetchList();
    const i = setInterval(fetchList, 5000);
    return () => clearInterval(i);
  }, [fetchList]);

  useEffect(() => {
    if (!selectedId) return;
    fetchDetail(selectedId);
    const i = setInterval(() => fetchDetail(selectedId), 6000);
    return () => clearInterval(i);
  }, [selectedId, fetchDetail]);

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
      <Header />
      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_2fr]">
        <div className="space-y-4">
          <StartForm
            onStarted={() => {
              fetchList();
              setError(null);
            }}
            onError={(e) => setError(e)}
          />
          <RunList
            runs={runs}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onStop={async (id) => {
              await api.replayStop(id);
              fetchList();
            }}
            onDelete={async (id) => {
              await api.replayDelete(id);
              if (selectedId === id) setSelectedId(null);
              fetchList();
            }}
            onDeleteAll={async () => {
              await api.replayDeleteAll();
              setSelectedId(null);
              fetchList();
            }}
          />
          <AdminBackfillBlock onError={(e) => setError(e)} />
        </div>
        <div>
          {error && (
            <div
              className="mb-3 border px-3 py-2 text-sm"
              style={{
                borderColor: "var(--color-crimson)",
                fontFamily: "var(--font-mono)",
              }}
            >
              {error}
            </div>
          )}
          {detail ? (
            <DetailView detail={detail} />
          ) : (
            <EmptyDetailView />
          )}
        </div>
      </div>
    </main>
  );
}

function Header() {
  return (
    <header className="flex items-baseline justify-between">
      <div>
        <p
          className="text-[10px] uppercase tracking-[0.3em]"
          style={{
            color: "var(--color-gold)",
            fontFamily: "var(--font-serif)",
          }}
        >
          · PHASE 6 · THE LIVING ORGANISM ·
        </p>
        <h1
          style={{
            fontFamily: "var(--font-deco)",
            fontSize: "var(--fs-hero)",
            letterSpacing: ".05em",
            color: "var(--color-warm-white)",
          }}
        >
          REPLAY
        </h1>
        <p
          className="max-w-xl text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-body)" }}
        >
          L&apos;organismo evolutivo cammina nella storia. Si re-evolve ogni 14
          giorni di tempo simulato, sopravvive ai regime change, o muore in modo
          tracciabile. Replay persistito server-side — puoi chiudere la pagina e
          tornare quando vuoi.
        </p>
      </div>
      <Link
        href="/"
        className="text-sm hover:underline"
        style={{
          color: "var(--color-gold)",
          fontFamily: "var(--font-serif)",
          letterSpacing: ".2em",
        }}
      >
        ← HOME
      </Link>
    </header>
  );
}

function StartForm({
  onStarted,
  onError,
}: {
  onStarted: () => void;
  onError: (e: string) => void;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const [name, setName] = useState("Replay BTC");
  const [symbol, setSymbol] = useState("BTC/USDT");
  const [startDate, setStartDate] = useState("2022-01-01");
  const [endDate, setEndDate] = useState("2023-01-01");
  const [retrainCadence, setRetrainCadence] = useState(14);
  const [lookback, setLookback] = useState(180);
  const [popSize, setPopSize] = useState(20);
  const [generations, setGenerations] = useState(8);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    setSubmitting(true);
    try {
      const params: ReplayStartParams = {
        name,
        symbol,
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        retrain_cadence_days: retrainCadence,
        lookback_days: lookback,
        ga_pop_size: popSize,
        ga_generations: generations,
      };
      await api.replayStart(params);
      onStarted();
    } catch (e) {
      onError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      className="border bg-[--color-surface-card] p-4"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <h2
        className="mb-3 text-[12px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        Avvia nuovo Replay
      </h2>
      <div className="grid grid-cols-2 gap-3 text-xs" style={{ fontFamily: "var(--font-mono)" }}>
        <Field label="Nome">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="Symbol">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          >
            <option value="BTC/USDT">BTC/USDT</option>
            <option value="ETH/USDT">ETH/USDT</option>
          </select>
        </Field>
        <Field label="Start date">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="End date">
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="Retrain ogni (giorni)">
          <input
            type="number"
            value={retrainCadence}
            onChange={(e) => setRetrainCadence(Number(e.target.value))}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="Lookback (giorni)">
          <input
            type="number"
            value={lookback}
            onChange={(e) => setLookback(Number(e.target.value))}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="Pop size GA">
          <input
            type="number"
            value={popSize}
            onChange={(e) => setPopSize(Number(e.target.value))}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
        <Field label="Generations">
          <input
            type="number"
            value={generations}
            onChange={(e) => setGenerations(Number(e.target.value))}
            className="w-full bg-[--color-surface-elevated] px-2 py-1.5 text-[--color-text-primary]"
            style={{ border: "1px solid var(--color-surface-border)" }}
          />
        </Field>
      </div>
      <button
        onClick={submit}
        disabled={submitting}
        className="mt-3 w-full py-2 text-xs uppercase tracking-[0.25em] disabled:opacity-50"
        style={{
          background: "var(--color-btc-orange)",
          color: "var(--color-void)",
          fontFamily: "var(--font-serif)",
          fontWeight: 700,
        }}
      >
        {submitting ? "Avvio..." : "◆ Avvia Replay"}
      </button>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span
        className="block text-[10px] uppercase tracking-[0.2em]"
        style={{ color: "var(--color-text-secondary)", fontFamily: "var(--font-serif)" }}
      >
        {label}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function RunList({
  runs,
  selectedId,
  onSelect,
  onStop,
  onDelete,
  onDeleteAll,
}: {
  runs: ReplayRunSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onStop: (id: string) => void | Promise<void>;
  onDelete: (id: string) => void | Promise<void>;
  onDeleteAll: () => void | Promise<void>;
}) {
  return (
    <section
      className="border bg-[--color-surface-card]"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <div className="flex items-center justify-between px-3 py-2">
        <h2
          className="text-[12px] uppercase tracking-[0.2em]"
          style={{
            fontFamily: "var(--font-serif)",
            color: "var(--color-gold)",
          }}
        >
          Runs ({runs.length})
        </h2>
        {runs.length > 0 && (
          <button
            onClick={() => {
              if (confirm("Cancellare TUTTI i replay dal DB?")) onDeleteAll();
            }}
            className="text-[10px] uppercase tracking-[0.2em]"
            style={{
              color: "var(--color-crimson)",
              fontFamily: "var(--font-serif)",
            }}
          >
            wipe all
          </button>
        )}
      </div>
      <ul className="max-h-[400px] overflow-y-auto">
        {runs.map((r) => (
          <li
            key={r.id}
            className="cursor-pointer border-t border-[--color-surface-border]/40 px-3 py-2 hover:bg-[--color-surface-elevated]"
            onClick={() => onSelect(r.id)}
            style={{
              background:
                selectedId === r.id ? "var(--color-surface-elevated)" : undefined,
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
          >
            <div className="flex items-center justify-between">
              <span
                style={{
                  color: VERDICT_COLORS[r.status] || "var(--color-text-secondary)",
                  fontFamily: "var(--font-serif)",
                  letterSpacing: ".15em",
                  fontSize: 10,
                  textTransform: "uppercase",
                }}
              >
                {r.status}
              </span>
              <span style={{ color: "var(--color-text-muted)" }}>
                {r.id.slice(0, 8)}
              </span>
            </div>
            <div className="mt-1 text-[--color-text-primary]">
              {r.name} · {r.symbol}
            </div>
            <div
              className="mt-1 flex items-center justify-between"
              style={{ color: "var(--color-text-secondary)" }}
            >
              <span>
                eq=${r.current_equity.toFixed(0)} · {r.progress_pct.toFixed(1)}%
              </span>
              <span>{r.n_retrains}r · {r.n_kill_switch_events}k</span>
            </div>
            <div className="mt-1 flex gap-2">
              {(r.status === "running" || r.status === "pending") && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    if (confirm("Stop replay?")) onStop(r.id);
                  }}
                  className="text-[10px] uppercase tracking-[0.15em]"
                  style={{
                    color: "var(--color-crimson)",
                    fontFamily: "var(--font-serif)",
                  }}
                >
                  stop
                </button>
              )}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm("Cancellare questo replay?")) onDelete(r.id);
                }}
                className="text-[10px] uppercase tracking-[0.15em]"
                style={{
                  color: "var(--color-crimson)",
                  fontFamily: "var(--font-serif)",
                }}
              >
                delete
              </button>
            </div>
          </li>
        ))}
        {runs.length === 0 && (
          <li
            className="px-3 py-6 text-center text-[--color-text-muted]"
            style={{ fontFamily: "var(--font-body)" }}
          >
            Nessun replay. Avvianeuno qui sopra.
          </li>
        )}
      </ul>
    </section>
  );
}

function AdminBackfillBlock({ onError }: { onError: (e: string) => void }) {
  const [start, setStart] = useState("2018-01-01");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const launch = async () => {
    setRunning(true);
    setMsg(null);
    try {
      const r = await api.adminBackfill({
        symbols: ["BTC/USDT", "ETH/USDT"],
        timeframes: ["1h", "4h", "1d"],
        start_date: new Date(start).toISOString(),
      });
      setMsg(r.message);
    } catch (e) {
      onError(String(e));
    } finally {
      setRunning(false);
    }
  };
  return (
    <section
      className="border bg-[--color-surface-card] p-3 text-xs"
      style={{
        borderColor: "var(--color-surface-border)",
        borderStyle: "dashed",
        fontFamily: "var(--font-mono)",
      }}
    >
      <h3
        className="mb-2 text-[10px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        · Admin · Historical backfill ·
      </h3>
      <div className="flex items-center gap-2">
        <input
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className="bg-[--color-surface-elevated] px-2 py-1"
          style={{ border: "1px solid var(--color-surface-border)" }}
        />
        <button
          onClick={launch}
          disabled={running}
          className="px-3 py-1 text-[10px] uppercase tracking-[0.2em]"
          style={{
            border: "1px solid var(--color-gold)",
            color: "var(--color-gold)",
            fontFamily: "var(--font-serif)",
          }}
        >
          {running ? "..." : "Backfill BTC+ETH"}
        </button>
      </div>
      {msg && (
        <p className="mt-2 text-[--color-text-secondary]">{msg}</p>
      )}
    </section>
  );
}

function EmptyDetailView() {
  return (
    <div
      className="flex h-[600px] items-center justify-center border bg-[--color-surface-card]"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <p
        className="text-[--color-text-muted]"
        style={{ fontFamily: "var(--font-body)", fontSize: "var(--fs-lg)" }}
      >
        Seleziona un replay per vedere l&apos;equity curve e l&apos;evoluzione.
      </p>
    </div>
  );
}

function DetailView({ detail }: { detail: ReplayDetailResponse }) {
  const { summary, equity_curve, retrain_events } = detail;
  const equityData = useMemo(
    () =>
      equity_curve.map((p) => ({
        t: new Date(p.t).getTime(),
        eq: p.equity,
        dd: p.drawdown_pct,
        pos: p.position_size_pct,
        regime: p.regime,
        trades: p.n_trades_so_far,
      })),
    [equity_curve],
  );
  const retrainTimes = useMemo(
    () => retrain_events.map((e) => new Date(e.t).getTime()),
    [retrain_events],
  );
  const killSwitchTimes = useMemo(
    () =>
      retrain_events
        .filter((e) => e.trigger === "kill_switch")
        .map((e) => new Date(e.t).getTime()),
    [retrain_events],
  );

  return (
    <div className="space-y-4">
      <SummaryCard summary={summary} />
      <EquityChart data={equityData} retrains={retrainTimes} kills={killSwitchTimes} />
      <DrawdownChart data={equityData} retrains={retrainTimes} />
      <RegimeBreakdown data={equityData} />
      <RetrainsTable events={retrain_events} />
    </div>
  );
}

function SummaryCard({ summary }: { summary: ReplayRunSummary }) {
  const fm = (summary.final_metrics ?? {}) as Record<string, unknown>;
  const sharpe = typeof fm["sharpe"] === "number" ? (fm["sharpe"] as number) : null;
  const totalReturn = typeof fm["total_return"] === "number" ? (fm["total_return"] as number) : null;
  const dd = typeof fm["max_drawdown"] === "number" ? (fm["max_drawdown"] as number) : null;
  const baselines = fm["baselines"] as Record<string, Record<string, number>> | undefined;
  const bh = baselines?.buy_hold;
  const tb = baselines?.textbook_council;
  const gos = baselines?.ga_one_shot;
  const alphaBH = typeof fm["alpha_vs_buy_hold"] === "number" ? (fm["alpha_vs_buy_hold"] as number) : null;
  const alphaTB = typeof fm["alpha_vs_textbook"] === "number" ? (fm["alpha_vs_textbook"] as number) : null;
  const alphaGOS = typeof fm["alpha_vs_ga_one_shot"] === "number" ? (fm["alpha_vs_ga_one_shot"] as number) : null;
  const dsr = fm["deflated_sharpe"] as Record<string, number | string> | undefined;
  return (
    <section
      className="border bg-[--color-surface-card] p-4"
      style={{ borderColor: VERDICT_COLORS[summary.status] || "var(--color-gold)" }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <p
            className="text-[10px] uppercase tracking-[0.25em]"
            style={{
              color: VERDICT_COLORS[summary.status] || "var(--color-text-secondary)",
              fontFamily: "var(--font-serif)",
            }}
          >
            STATUS · {summary.status.toUpperCase()}
          </p>
          <h2
            style={{
              fontFamily: "var(--font-deco)",
              fontSize: "var(--fs-2xl)",
              color: "var(--color-warm-white)",
              marginTop: 4,
            }}
          >
            {summary.name}
          </h2>
          <p
            className="mt-1 text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}
          >
            {summary.symbol} · equity = ${summary.current_equity.toFixed(2)} ·{" "}
            {summary.n_retrains} retrains · {summary.n_kill_switch_events} kill events
          </p>
          {summary.error && (
            <p className="mt-2 text-[--color-crimson]" style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
              ⚠ {summary.error}
            </p>
          )}
        </div>
        <div className="text-right" style={{ fontFamily: "var(--font-mono)" }}>
          <p className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]">
            Progress
          </p>
          <p
            style={{
              fontFamily: "var(--font-deco)",
              fontSize: "2rem",
              color: "var(--color-btc-orange)",
            }}
          >
            {summary.progress_pct.toFixed(1)}%
          </p>
        </div>
      </div>
      {(sharpe !== null || totalReturn !== null) && (
        <>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label="Sharpe" value={sharpe?.toFixed(2) ?? "—"} />
          <Metric
            label="Total return"
            value={
              totalReturn !== null
                ? `${totalReturn >= 0 ? "+" : ""}${(totalReturn * 100).toFixed(2)}%`
                : "—"
            }
            color={totalReturn !== null && totalReturn >= 0 ? "#00ff99" : "var(--color-crimson)"}
          />
          <Metric label="Max DD" value={dd !== null ? `${(dd * 100).toFixed(2)}%` : "—"} color="var(--color-crimson)" />
          <Metric
            label="Final equity"
            value={typeof fm["final_equity"] === "number" ? `$${(fm["final_equity"] as number).toFixed(0)}` : "—"}
          />
        </div>
        {dsr && (
          <div className="mt-4 border p-3" style={{ borderColor: "var(--color-gold)", borderStyle: "dashed" }}>
            <p className="text-[10px] uppercase tracking-[0.25em] text-[--color-gold]" style={{ fontFamily: "var(--font-serif)" }}>
              · DEFLATED SHARPE RATIO · BAILEY &amp; LÓPEZ DE PRADO ·
            </p>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-3" style={{ fontFamily: "var(--font-mono)" }}>
              <DsrCell label="DSR" value={typeof dsr.dsr === "number" ? (dsr.dsr as number).toFixed(3) : "—"} verdict={dsr.verdict as string} />
              <DsrCell label="PSR" value={typeof dsr.psr === "number" ? (dsr.psr as number).toFixed(3) : "—"} />
              <DsrCell label="SR threshold" value={typeof dsr.sr_threshold === "number" ? (dsr.sr_threshold as number).toFixed(3) : "—"} />
              <DsrCell label="N trials" value={typeof dsr.n_trials === "number" ? String(dsr.n_trials) : "—"} />
            </div>
            <p className="mt-2 text-[10px] text-[--color-text-muted]" style={{ fontFamily: "var(--font-body)" }}>
              DSR &lt; 0.50 = falso positivo · 0.50-0.80 = marginale · 0.80-0.95 = significativo · &gt; 0.95 = altamente significativo. Corregge per multiple testing (N trial) e non-normalità (skew/kurtosis).
            </p>
          </div>
        )}

        {/* Baselines comparison */}
        {(bh || tb || gos) && (
          <div className="mt-6">
            <p
              className="mb-2 text-[10px] uppercase tracking-[0.25em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              · BASELINES · ALPHA RATE ·
            </p>
            <div className="overflow-x-auto border" style={{ borderColor: "var(--color-gold)", borderStyle: "dashed" }}>
              <table className="w-full text-xs" style={{ fontFamily: "var(--font-mono)" }}>
                <thead>
                  <tr
                    className="border-b border-[--color-surface-border] text-[10px] uppercase tracking-[0.2em] text-[--color-gold]"
                    style={{ fontFamily: "var(--font-serif)" }}
                  >
                    <th className="px-3 py-2 text-left">Strategy</th>
                    <th className="px-3 py-2 text-right">Sharpe</th>
                    <th className="px-3 py-2 text-right">Return</th>
                    <th className="px-3 py-2 text-right">Max DD</th>
                    <th className="px-3 py-2 text-right">Alpha vs replay</th>
                  </tr>
                </thead>
                <tbody>
                  <BaselineRow label="REPLAY (adaptive Council)" sharpe={sharpe} ret={totalReturn} dd={dd} alpha={0} isPrimary />
                  {bh && (
                    <BaselineRow
                      label="Buy & Hold"
                      sharpe={typeof bh.sharpe === "number" ? bh.sharpe : null}
                      ret={typeof bh.total_return === "number" ? bh.total_return : null}
                      dd={typeof bh.max_drawdown === "number" ? bh.max_drawdown : null}
                      alpha={alphaBH}
                    />
                  )}
                  {tb && (
                    <BaselineRow
                      label="Textbook Council (no GA)"
                      sharpe={typeof tb.sharpe === "number" ? tb.sharpe : null}
                      ret={typeof tb.total_return === "number" ? tb.total_return : null}
                      dd={typeof tb.max_drawdown === "number" ? tb.max_drawdown : null}
                      alpha={alphaTB}
                    />
                  )}
                  {gos && (
                    <BaselineRow
                      label="GA-one-shot (no re-evolve)"
                      sharpe={typeof gos.sharpe === "number" ? gos.sharpe : null}
                      ret={typeof gos.total_return === "number" ? gos.total_return : null}
                      dd={typeof gos.max_drawdown === "number" ? gos.max_drawdown : null}
                      alpha={alphaGOS}
                    />
                  )}
                </tbody>
              </table>
            </div>
            <p
              className="mt-2 text-[10px] text-[--color-text-muted]"
              style={{ fontFamily: "var(--font-body)" }}
            >
              Alpha = Sharpe replay − Sharpe baseline. Positivo = il sistema adattivo aggiunge valore. Negativo = stesso risultato del baseline o peggio.
            </p>
          </div>
        )}
        </>
      )}
    </section>
  );
}

function DsrCell({ label, value, verdict }: { label: string; value: string; verdict?: string }) {
  const color = !verdict ? "var(--color-text-primary)" :
    verdict === "highly_significant" ? "#00ff99" :
    verdict === "significant" ? "var(--color-gold)" :
    verdict === "marginal" ? "var(--color-btc-orange)" :
    "var(--color-crimson)";
  return (
    <div className="border bg-[--color-surface-elevated] px-2 py-1.5" style={{ borderColor: "var(--color-surface-border)" }}>
      <p className="text-[9px] uppercase tracking-[0.2em] text-[--color-text-secondary]" style={{ fontFamily: "var(--font-serif)" }}>{label}</p>
      <p style={{ fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 700, color }}>{value}</p>
      {verdict && (
        <p className="text-[9px] uppercase tracking-[0.15em]" style={{ color, fontFamily: "var(--font-serif)", marginTop: 2 }}>
          {verdict.replace("_", " ")}
        </p>
      )}
    </div>
  );
}

function BaselineRow({
  label,
  sharpe,
  ret,
  dd,
  alpha,
  isPrimary = false,
}: {
  label: string;
  sharpe: number | null;
  ret: number | null;
  dd: number | null;
  alpha: number | null;
  isPrimary?: boolean;
}) {
  return (
    <tr
      className="border-b border-[--color-surface-border]/40"
      style={isPrimary ? { background: "var(--color-surface-elevated)" } : {}}
    >
      <td
        className="px-3 py-2 text-[--color-text-primary]"
        style={isPrimary ? { color: "var(--color-gold)", fontWeight: 700 } : {}}
      >
        {label}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color: sharpe === null ? "var(--color-text-muted)" : sharpe >= 0 ? "var(--color-text-primary)" : "var(--color-crimson)",
        }}
      >
        {sharpe !== null ? sharpe.toFixed(2) : "—"}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{ color: ret !== null && ret >= 0 ? "#00ff99" : "var(--color-crimson)" }}
      >
        {ret !== null ? `${ret >= 0 ? "+" : ""}${(ret * 100).toFixed(2)}%` : "—"}
      </td>
      <td className="px-3 py-2 text-right text-[--color-text-secondary]">
        {dd !== null ? `${(dd * 100).toFixed(2)}%` : "—"}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color: alpha === null ? "var(--color-text-muted)" : alpha > 0 ? "#00ff99" : alpha < 0 ? "var(--color-crimson)" : "var(--color-text-secondary)",
          fontWeight: isPrimary ? 400 : 700,
        }}
      >
        {isPrimary ? "—" : alpha !== null ? `${alpha >= 0 ? "+" : ""}${alpha.toFixed(2)}` : "—"}
      </td>
    </tr>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      className="border bg-[--color-surface-elevated] px-3 py-2"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <p
        className="text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {label}
      </p>
      <p
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 18,
          fontWeight: 700,
          color: color || "var(--color-text-primary)",
        }}
      >
        {value}
      </p>
    </div>
  );
}

type EquityRow = {
  t: number;
  eq: number;
  dd: number;
  pos: number;
  regime: string | null;
  trades: number;
};

function EquityChart({
  data,
  retrains,
  kills,
}: {
  data: EquityRow[];
  retrains: number[];
  kills: number[];
}) {
  return (
    <section
      className="border bg-[--color-surface-card] p-4"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <h3
        className="mb-2 text-[12px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        Equity Curve · Retrain Events · Kill Switch
      </h3>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-surface-border)" />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)}
            stroke="var(--color-text-muted)"
            fontSize={10}
          />
          <YAxis stroke="var(--color-text-muted)" fontSize={10} />
          <Tooltip
            contentStyle={{
              background: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
            labelFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)}
          />
          <Legend wrapperStyle={{ fontFamily: "var(--font-serif)", fontSize: 11, letterSpacing: ".15em", textTransform: "uppercase" }} />
          <Line type="monotone" dataKey="eq" stroke="var(--color-gold)" strokeWidth={2} dot={false} name="Equity" />
          {retrains.map((t) => (
            <ReferenceLine key={`r-${t}`} x={t} stroke="var(--color-btc-orange)" strokeOpacity={0.3} strokeDasharray="2 2" />
          ))}
          {kills.map((t) => (
            <ReferenceLine key={`k-${t}`} x={t} stroke="var(--color-crimson)" strokeOpacity={0.7} strokeWidth={2} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      <p
        className="mt-2 text-[10px] text-[--color-text-muted]"
        style={{ fontFamily: "var(--font-body)" }}
      >
        Linee tratteggiate arancio: retraining schedulati. Linee piene crimson: kill switch (drawdown 30d &lt; -10%).
      </p>
    </section>
  );
}

function DrawdownChart({ data, retrains }: { data: EquityRow[]; retrains: number[] }) {
  return (
    <section
      className="border bg-[--color-surface-card] p-4"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <h3
        className="mb-2 text-[12px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        Drawdown · Position Size
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-surface-border)" />
          <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]}
                 tickFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)}
                 stroke="var(--color-text-muted)" fontSize={10} />
          <YAxis yAxisId="left" stroke="var(--color-crimson)" fontSize={10} />
          <YAxis yAxisId="right" orientation="right" stroke="var(--color-btc-orange)" fontSize={10} />
          <Tooltip
            contentStyle={{
              background: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
            labelFormatter={(v) => new Date(v as number).toISOString().slice(0, 10)}
          />
          <Legend wrapperStyle={{ fontFamily: "var(--font-serif)", fontSize: 11, letterSpacing: ".15em", textTransform: "uppercase" }} />
          <Line yAxisId="left" type="monotone" dataKey="dd" stroke="var(--color-crimson)" strokeWidth={1.5} dot={false} name="Drawdown %" />
          <Line yAxisId="right" type="monotone" dataKey="pos" stroke="var(--color-btc-orange)" strokeWidth={1.5} dot={false} name="Position %" />
          <ReferenceLine yAxisId="left" y={-10} stroke="var(--color-crimson)" strokeDasharray="4 4" />
        </LineChart>
      </ResponsiveContainer>
    </section>
  );
}

function RegimeBreakdown({ data }: { data: EquityRow[] }) {
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of data) {
      const k = r.regime || "unknown";
      c[k] = (c[k] || 0) + 1;
    }
    return Object.entries(c).map(([k, v]) => ({ regime: k, count: v }));
  }, [data]);
  if (counts.length === 0) return null;
  return (
    <section
      className="border bg-[--color-surface-card] p-4"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <h3
        className="mb-2 text-[12px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        Tempo nei regimi (snapshots)
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={counts}>
          <XAxis dataKey="regime" stroke="var(--color-text-muted)" fontSize={9} />
          <YAxis stroke="var(--color-text-muted)" fontSize={10} />
          <Tooltip
            contentStyle={{
              background: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
          />
          <Bar dataKey="count" fill="var(--color-gold)" />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}

function RetrainsTable({ events }: { events: ReplayRetrainEvent[] }) {
  if (events.length === 0) return null;
  return (
    <section
      className="border bg-[--color-surface-card] overflow-x-auto"
      style={{ borderColor: "var(--color-surface-border)" }}
    >
      <h3
        className="px-4 py-2 text-[12px] uppercase tracking-[0.2em]"
        style={{ fontFamily: "var(--font-serif)", color: "var(--color-gold)" }}
      >
        Retrain Events ({events.length})
      </h3>
      <table className="w-full text-xs" style={{ fontFamily: "var(--font-mono)" }}>
        <thead>
          <tr
            className="border-y border-[--color-surface-border] text-[10px] uppercase tracking-[0.2em] text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            <th className="px-3 py-2 text-left">When</th>
            <th className="px-3 py-2 text-left">Trigger</th>
            <th className="px-3 py-2 text-right">Sharpe train</th>
            <th className="px-3 py-2 text-right">Trades train</th>
            <th className="px-3 py-2 text-right">Elapsed</th>
            <th className="px-3 py-2 text-right">Equity</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e, i) => {
            const o = e.organism as Record<string, number | string | unknown>;
            const sharpe = typeof o.sharpe_train === "number" ? o.sharpe_train : null;
            const trades = typeof o.n_trades_train === "number" ? o.n_trades_train : 0;
            const color =
              e.trigger === "kill_switch"
                ? "var(--color-crimson)"
                : e.trigger === "initial"
                ? "var(--color-gold)"
                : "var(--color-text-secondary)";
            return (
              <tr key={i} className="border-b border-[--color-surface-border]/40">
                <td className="px-3 py-1.5 text-[--color-text-primary]">
                  {new Date(e.t).toISOString().slice(0, 10)}
                </td>
                <td className="px-3 py-1.5" style={{ color, fontFamily: "var(--font-serif)", textTransform: "uppercase", letterSpacing: ".15em", fontSize: 10 }}>
                  {e.trigger.replace("_", " ")}
                </td>
                <td className="px-3 py-1.5 text-right" style={{ color: sharpe !== null && sharpe >= 0 ? "var(--color-text-primary)" : "var(--color-crimson)" }}>
                  {sharpe !== null ? sharpe.toFixed(2) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right text-[--color-text-secondary]">{trades}</td>
                <td className="px-3 py-1.5 text-right text-[--color-text-secondary]">{e.elapsed_seconds.toFixed(1)}s</td>
                <td className="px-3 py-1.5 text-right text-[--color-text-primary]">${e.equity_at_retrain.toFixed(0)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
