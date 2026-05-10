"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ApiError,
  api,
  type GaRunSummary,
  type OosEvolutionPoint,
  type OosResultResponse,
  type OosStrategyOut,
} from "@/lib/api";

const TEST_PRESETS = [
  { label: "30 giorni", days: 30 },
  { label: "60 giorni", days: 60 },
  { label: "90 giorni", days: 90 },
  { label: "180 giorni", days: 180 },
  { label: "1 anno", days: 365 },
] as const;

const VERDICT_COLORS: Record<string, string> = {
  robust: "#00ff99",
  mixed: "#f4a261",
  overfit: "#e63946",
  no_signal: "#9898a8",
  unknown: "#9898a8",
};

export default function OosPage() {
  const [runs, setRuns] = useState<GaRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [testDays, setTestDays] = useState(90);
  const [topK, setTopK] = useState(10);
  const [initialCash, setInitialCash] = useState(10000);

  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<OosResultResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    try {
      const r = await api.listGaRuns();
      const completed = r.runs.filter((run) => run.status === "completed");
      setRuns(completed);
      if (completed.length > 0 && !selectedRunId) {
        setSelectedRunId(completed[0].population_id);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load GA runs");
    }
  }, [selectedRunId]);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  const handleValidate = async () => {
    if (!selectedRunId) {
      setError("Seleziona un GA run completato");
      return;
    }
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.oosValidate(selectedRunId, testDays, topK, initialCash);
      setResult(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "OOS validation failed");
    } finally {
      setRunning(false);
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
              Phase 6 · Out-of-Sample Validation
            </p>
            <h1
              className="text-3xl md:text-5xl"
              style={{
                fontFamily: "var(--font-deco)",
                letterSpacing: "0.08em",
              }}
            >
              The Reckoning
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[--color-text-secondary]">
              Train su dati storici, replay sul periodo successivo. Le strategie
              evolute reggono fuori campione, o il GA ha solo memorizzato il
              passato? Il sistema ti dà un verdetto onesto.
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

        <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-6">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                GA run completato
              </span>
              <select
                value={selectedRunId}
                onChange={(e) => setSelectedRunId(e.target.value)}
                className="border border-[--color-surface-border] bg-[--color-surface-card] px-2 py-2 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {runs.length === 0 && (
                  <option value="">Nessun run disponibile</option>
                )}
                {runs.map((r) => (
                  <option key={r.population_id} value={r.population_id}>
                    {r.population_id} · {r.strategy_id} · {r.symbol} {r.timeframe}
                    {r.best_sharpe_robust !== null
                      ? ` · S=${r.best_sharpe_robust.toFixed(2)}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Test period
              </span>
              <select
                value={testDays}
                onChange={(e) => setTestDays(Number(e.target.value))}
                className="border border-[--color-surface-border] bg-[--color-surface-card] px-2 py-2 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {TEST_PRESETS.map((p) => (
                  <option key={p.days} value={p.days}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Top K strategie
              </span>
              <input
                type="number"
                min={1}
                max={50}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value))}
                className="border border-[--color-surface-border] bg-[--color-surface-elevated] px-2 py-1.5 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Initial cash USDT
              </span>
              <input
                type="number"
                min={1000}
                step={1000}
                value={initialCash}
                onChange={(e) => setInitialCash(Number(e.target.value))}
                className="border border-[--color-surface-border] bg-[--color-surface-elevated] px-2 py-1.5 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              />
            </label>
          </div>

          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={handleValidate}
              disabled={running || !selectedRunId}
              className="px-5 py-2 text-xs uppercase tracking-[0.25em]"
              style={{
                fontFamily: "var(--font-serif)",
                background: running ? "var(--color-surface-elevated)" : "#f7931a",
                color: running ? "var(--color-text-muted)" : "var(--color-void)",
                border: "1px solid #f7931a",
                cursor: running ? "wait" : "pointer",
              }}
            >
              {running ? "Validating… (pochi secondi)" : "◆ Run OOS Validation"}
            </button>
          </div>
        </section>

        {result && <OosReport result={result} />}

        <footer
          className="mt-12 border-t border-[--color-surface-border] pt-4 text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          Train period viene dedotto dal GA run · Test period parte subito dopo
          train_end
        </footer>
      </div>
    </main>
  );
}

function OosReport({ result }: { result: OosResultResponse }) {
  const verdictColor = VERDICT_COLORS[result.overall_verdict] || "var(--color-gold)";
  const verdictLabel = result.overall_verdict.toUpperCase();

  return (
    <>
      {/* Verdict header */}
      <section
        className="mb-6 border-2 px-6 py-5"
        style={{
          borderColor: verdictColor,
          background: "var(--color-surface-card)",
        }}
      >
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p
              className="text-[10px] uppercase tracking-[0.4em]"
              style={{
                fontFamily: "var(--font-serif)",
                color: "var(--color-text-secondary)",
              }}
            >
              Overall verdict
            </p>
            <p
              className="mt-1 text-3xl"
              style={{
                fontFamily: "var(--font-mono)",
                color: verdictColor,
                letterSpacing: "0.08em",
              }}
            >
              {verdictLabel}
            </p>
          </div>
          <div
            className="grid grid-cols-4 gap-4 text-right text-xs"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            <Counter label="robust" value={result.n_robust} color="#00ff99" />
            <Counter label="mixed" value={result.n_mixed} color="#f4a261" />
            <Counter label="overfit" value={result.n_overfit} color="#e63946" />
            <Counter label="no signal" value={result.n_no_signal} color="#9898a8" />
          </div>
        </div>
        <p
          className="mt-3 text-sm"
          style={{
            color: "var(--color-text-secondary)",
            fontFamily: "var(--font-body, var(--font-serif))",
            lineHeight: 1.6,
          }}
        >
          {result.overall_reason}
        </p>
      </section>

      {/* Evolution chart — il GA migliora generazione dopo generazione? */}
      {result.evolution_curve.length > 0 && (
        <section className="mb-6">
          <h2
            className="mb-3 text-sm uppercase tracking-[0.3em] text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Evolution × OOS · per generation
          </h2>
          <p className="mb-3 text-xs text-[--color-text-secondary]">
            Per ogni generazione del GA, il best chromosome è stato testato
            fuori campione. Se la linea <strong style={{ color: "#7799ff" }}>blu</strong> (test)
            sale insieme alla <strong style={{ color: "#c5a059" }}>gold</strong>{" "}
            (train), il GA generalizza. Se diverge, sta overfittando.
          </p>
          <EvolutionChart points={result.evolution_curve} />
        </section>
      )}

      {/* Period summary */}
      <section
        className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4"
        style={{ fontFamily: "var(--font-mono)" }}
      >
        <Card label="Strategy" value={result.strategy_id} />
        <Card label="Symbol · TF" value={`${result.symbol} ${result.timeframe}`} />
        <Card
          label="Train"
          value={`${formatDate(result.train_start)} → ${formatDate(result.train_end)}`}
        />
        <Card
          label="Test"
          value={`${formatDate(result.test_start)} → ${formatDate(result.test_end)} (${result.test_days}d)`}
        />
      </section>

      {/* Per-strategy table */}
      <section className="border border-[--color-surface-border] bg-[--color-surface-card] overflow-x-auto">
        <table
          className="w-full text-xs"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          <thead>
            <tr
              className="border-b border-[--color-surface-border] text-[10px] uppercase tracking-[0.2em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              <th className="px-3 py-2 text-left">#</th>
              <th className="px-3 py-2 text-left">Verdict</th>
              <th className="px-3 py-2 text-right">Sharpe train</th>
              <th className="px-3 py-2 text-right">Sharpe test</th>
              <th className="px-3 py-2 text-right">Δ%</th>
              <th className="px-3 py-2 text-right">Return test</th>
              <th className="px-3 py-2 text-right">DD test</th>
              <th className="px-3 py-2 text-right">Trades</th>
              <th className="px-3 py-2 text-right">Win</th>
              <th className="px-3 py-2 text-right">Final eq.</th>
              <th className="px-3 py-2 text-left">Chromosome</th>
            </tr>
          </thead>
          <tbody>
            {result.strategies.map((s) => (
              <StrategyRow key={s.rank} s={s} />
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function StrategyRow({ s }: { s: OosStrategyOut }) {
  const color = VERDICT_COLORS[s.verdict] || "var(--color-text-muted)";
  return (
    <tr className="border-b border-[--color-surface-border]/40">
      <td className="px-3 py-2 text-[--color-gold]">{s.rank}</td>
      <td className="px-3 py-2">
        <span
          title={s.verdict_reason}
          className="border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em]"
          style={{
            fontFamily: "var(--font-serif)",
            borderColor: color,
            color,
          }}
        >
          {s.verdict.replace("_", " ")}
        </span>
      </td>
      <td className="px-3 py-2 text-right text-[--color-text-secondary]">
        {s.sharpe_train.toFixed(2)}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color:
            s.sharpe_test === null
              ? "var(--color-text-muted)"
              : s.sharpe_test >= 0
                ? "var(--color-text-primary)"
                : "var(--color-crimson)",
        }}
      >
        {s.sharpe_test !== null ? s.sharpe_test.toFixed(2) : "—"}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color:
            s.degradation_pct === null
              ? "var(--color-text-muted)"
              : s.degradation_pct >= -50
                ? "var(--color-text-secondary)"
                : "var(--color-crimson)",
        }}
      >
        {s.degradation_pct !== null
          ? `${s.degradation_pct >= 0 ? "+" : ""}${s.degradation_pct.toFixed(0)}%`
          : "—"}
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color: s.total_return_test >= 0 ? "#00ff99" : "#e63946",
        }}
      >
        {s.total_return_test >= 0 ? "+" : ""}
        {(s.total_return_test * 100).toFixed(2)}%
      </td>
      <td className="px-3 py-2 text-right text-[--color-text-secondary]">
        {(s.max_drawdown_test * 100).toFixed(2)}%
      </td>
      <td
        className="px-3 py-2 text-right"
        style={{
          color:
            s.n_trades_test < 3
              ? "var(--color-crimson)"
              : "var(--color-text-secondary)",
        }}
      >
        {s.n_trades_test}
      </td>
      <td className="px-3 py-2 text-right text-[--color-text-secondary]">
        {s.win_rate_test !== null
          ? `${(s.win_rate_test * 100).toFixed(0)}%`
          : "—"}
      </td>
      <td className="px-3 py-2 text-right text-[--color-text-primary]">
        {s.final_equity_test.toFixed(0)}
      </td>
      <td className="px-3 py-2 text-left text-[--color-text-muted]">
        {formatChromosome(s.chromosome)}
      </td>
    </tr>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-[--color-surface-border] bg-[--color-surface-card] px-3 py-2">
      <p
        className="text-[10px] uppercase tracking-[0.25em] text-[--color-text-secondary]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {label}
      </p>
      <p className="mt-1 text-sm text-[--color-text-primary]">{value}</p>
    </div>
  );
}

function Counter({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div>
      <p
        className="text-[9px] uppercase tracking-[0.2em]"
        style={{
          fontFamily: "var(--font-serif)",
          color: "var(--color-text-muted)",
        }}
      >
        {label}
      </p>
      <p className="mt-0.5 text-lg" style={{ color }}>
        {value}
      </p>
    </div>
  );
}

function EvolutionChart({ points }: { points: OosEvolutionPoint[] }) {
  const data = points.map((p) => ({
    generation: p.generation,
    sharpe_train: p.best_sharpe_robust_train,
    sharpe_test: p.best_sharpe_test,
    return_test_pct: p.best_total_return_test * 100,
    diversity: p.diversity,
  }));

  return (
    <div
      className="border border-[--color-surface-border] bg-[--color-surface-card] p-4"
      style={{ height: 360 }}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 16 }}>
          <CartesianGrid stroke="var(--color-surface-border)" strokeDasharray="2 4" />
          <XAxis
            dataKey="generation"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            stroke="var(--color-surface-border)"
            label={{
              value: "Generation",
              position: "insideBottom",
              offset: -4,
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-serif)",
              fontSize: 10,
            }}
          />
          <YAxis
            yAxisId="sharpe"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            stroke="var(--color-surface-border)"
            tickFormatter={(v) => v.toFixed(2)}
            width={50}
            label={{
              value: "Sharpe",
              angle: -90,
              position: "insideLeft",
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-serif)",
              fontSize: 10,
            }}
          />
          <YAxis
            yAxisId="return"
            orientation="right"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            stroke="var(--color-surface-border)"
            tickFormatter={(v) => `${v.toFixed(0)}%`}
            width={50}
            label={{
              value: "Return %",
              angle: 90,
              position: "insideRight",
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-serif)",
              fontSize: 10,
            }}
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
            formatter={(value: number, name: string) => {
              if (name === "return_test_pct") {
                return [`${value.toFixed(2)}%`, "Return test"];
              }
              if (name === "sharpe_train") {
                return [value !== null ? value.toFixed(3) : "—", "Sharpe train"];
              }
              if (name === "sharpe_test") {
                return [value !== null ? value.toFixed(3) : "—", "Sharpe test"];
              }
              return [value, name];
            }}
          />
          <Legend
            wrapperStyle={{
              fontFamily: "var(--font-serif)",
              fontSize: 10,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
            }}
          />
          <Line
            yAxisId="sharpe"
            type="monotone"
            dataKey="sharpe_train"
            name="Sharpe train (in-sample)"
            stroke="#c5a059"
            strokeWidth={2}
            dot={{ r: 3, fill: "#c5a059" }}
            isAnimationActive
          />
          <Line
            yAxisId="sharpe"
            type="monotone"
            dataKey="sharpe_test"
            name="Sharpe test (OOS)"
            stroke="#7799ff"
            strokeWidth={2}
            dot={{ r: 3, fill: "#7799ff" }}
            connectNulls
            isAnimationActive
          />
          <Line
            yAxisId="return"
            type="monotone"
            dataKey="return_test_pct"
            name="Return % test"
            stroke="#00ff99"
            strokeWidth={1.4}
            strokeDasharray="4 2"
            dot={false}
            isAnimationActive
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatDate(d: string): string {
  return new Date(d).toLocaleDateString("en-US", {
    year: "2-digit",
    month: "short",
    day: "numeric",
  });
}

function formatChromosome(c: Record<string, number | string>): string {
  return Object.entries(c)
    .map(([k, v]) => {
      if (typeof v === "number") {
        return `${k}=${Number.isInteger(v) ? v : v.toFixed(2)}`;
      }
      return `${k}=${v}`;
    })
    .join(", ");
}
