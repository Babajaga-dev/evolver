"use client";

/**
 * /sentiment — Fear & Greed Index overlay
 *
 * Visual che spiega l'evoluzione del macro-sentiment crypto:
 * - Daily F&G value (area chart, color-coded per zona)
 * - EMA-24w (Zhang-Watts arXiv 2512.02029 — predictor robusto OOS 1-3y)
 * - Zone bands (extreme fear / fear / neutral / greed / extreme greed)
 * - Summary metrics + backfill trigger
 *
 * Trading rationale: shock 1-std-dev sentiment riduce top-quartile returns
 * di 15-22 pp e median returns di 6-10 pp su 1-3 anni. Macro sentiment
 * batte ogni predittore endogeno (return realized, vol, momentum).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api, type FngPoint, type FngSeriesResponse, type FngStats } from "@/lib/api";

const ZONE_COLORS: Record<string, string> = {
  extreme_fear: "#8B1A1A",
  fear: "#C5630E",
  neutral: "#C5A059",
  greed: "#6A8E3A",
  extreme_greed: "#00FF99",
};

const ZONE_LABELS: Record<string, string> = {
  extreme_fear: "Extreme Fear",
  fear: "Fear",
  neutral: "Neutral",
  greed: "Greed",
  extreme_greed: "Extreme Greed",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("it-IT", { year: "numeric", month: "short", day: "2-digit" });
}

export default function SentimentPage() {
  const [data, setData] = useState<FngSeriesResponse | null>(null);
  const [stats, setStats] = useState<FngStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [backfillMessage, setBackfillMessage] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [s, st] = await Promise.all([
        api.fngSeries({ limit: 10000 }).catch(() => null),
        api.fngStats(),
      ]);
      setStats(st);
      setData(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento F&G");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const triggerBackfill = useCallback(async () => {
    try {
      setBackfilling(true);
      setBackfillMessage(null);
      const r = await api.fngBackfill(0);
      setBackfillMessage(r.message);
      // poll for completion (wait ~12s then refresh)
      setTimeout(() => {
        void fetchAll();
        setBackfilling(false);
      }, 12000);
    } catch (e) {
      setBackfillMessage(e instanceof Error ? e.message : "Errore backfill");
      setBackfilling(false);
    }
  }, [fetchAll]);

  const chartData = useMemo(() => {
    if (!data) return [];
    return data.points.map((p) => ({
      date: p.date,
      value: p.value,
      ema: p.ema_24w,
      zone: p.zone,
    }));
  }, [data]);

  const noData = !data || data.points.length === 0;

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-[var(--gold)]/30 pb-4">
          <h1 className="text-3xl font-bold tracking-wider text-[var(--gold)] uppercase">
            Sentiment · Fear &amp; Greed
          </h1>
          <p className="text-sm text-[var(--foreground)]/60 mt-1">
            Macro overlay basato sul paper Zhang-Watts arXiv 2512.02029 — EMA-24w del Fear &amp;
            Greed Index è il predictor cross-basket più stabile per crypto returns OOS 1-3 anni.
          </p>
        </header>

        {/* Backfill bar */}
        <section className="flex items-center gap-4 p-4 border border-[var(--gold)]/20 rounded bg-[var(--surface-card)]">
          <button
            type="button"
            onClick={triggerBackfill}
            disabled={backfilling}
            className="px-4 py-2 border-2 border-[var(--gold)] text-[var(--gold)] uppercase tracking-wider text-xs font-semibold hover:bg-[var(--gold)] hover:text-[var(--background)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {backfilling ? "Backfilling..." : "Backfill F&G (full history)"}
          </button>
          {backfillMessage && (
            <span className="text-xs text-[var(--foreground)]/70">{backfillMessage}</span>
          )}
          {stats && (
            <span className="ml-auto text-xs text-[var(--foreground)]/60">
              {stats.total_entries} entries in DB · latest:{" "}
              {stats.latest_date ? formatDate(stats.latest_date) : "—"} ({stats.latest_value ?? "—"})
            </span>
          )}
        </section>

        {/* Loading / error */}
        {loading && (
          <div className="p-8 text-center text-[var(--foreground)]/60">Caricamento serie F&amp;G...</div>
        )}
        {error && (
          <div className="p-4 border border-[#8B1A1A] bg-[#8B1A1A]/10 rounded text-[#FF6666]">
            {error}
          </div>
        )}
        {!loading && noData && !error && (
          <div className="p-8 text-center border border-[var(--gold)]/30 bg-[var(--surface-card)] rounded">
            <p className="text-[var(--foreground)]/80 mb-2">Nessun dato F&amp;G nel DB.</p>
            <p className="text-sm text-[var(--foreground)]/60">
              Clicca <strong>Backfill F&amp;G</strong> sopra per scaricare la storia completa dal 2018.
            </p>
          </div>
        )}

        {/* Summary cards */}
        {!noData && data && (
          <>
            <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <SummaryCard
                label="Current value"
                value={String(data.summary.current_value)}
                hint={data.summary.current_zone.toUpperCase()}
                color={ZONE_COLORS[data.summary.current_zone] ?? "#C5A059"}
              />
              <SummaryCard
                label="EMA-24w current"
                value={data.summary.current_ema_24w.toFixed(1)}
                hint={ZONE_LABELS[data.summary.current_zone] ?? "—"}
                color={ZONE_COLORS[data.summary.current_zone] ?? "#C5A059"}
              />
              <SummaryCard
                label="Mean value (lifetime)"
                value={data.summary.mean_value.toFixed(1)}
                hint={`range ${data.summary.min_value}–${data.summary.max_value}`}
              />
              <SummaryCard
                label="Extreme fear days"
                value={String(data.summary.n_extreme_fear_days)}
                hint="EMA-24w < 25"
                color="#8B1A1A"
              />
              <SummaryCard
                label="Extreme greed days"
                value={String(data.summary.n_extreme_greed_days)}
                hint="EMA-24w >= 75"
                color="#00FF99"
              />
            </section>

            {/* Main chart: F&G daily + EMA-24w + zone bands */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Evolution · Daily F&amp;G value + EMA-24w
              </h2>
              <ResponsiveContainer width="100%" height={420}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="fngArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#C5A059" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="#C5A059" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>

                  {/* Zone reference areas */}
                  <ReferenceArea y1={0} y2={25} fill="#8B1A1A" fillOpacity={0.06} />
                  <ReferenceArea y1={25} y2={45} fill="#C5630E" fillOpacity={0.05} />
                  <ReferenceArea y1={45} y2={55} fill="#C5A059" fillOpacity={0.04} />
                  <ReferenceArea y1={55} y2={75} fill="#6A8E3A" fillOpacity={0.05} />
                  <ReferenceArea y1={75} y2={100} fill="#00FF99" fillOpacity={0.06} />

                  <ReferenceLine y={25} stroke="#8B1A1A" strokeDasharray="3 3" strokeOpacity={0.5} />
                  <ReferenceLine y={50} stroke="#C5A059" strokeDasharray="3 3" strokeOpacity={0.4} />
                  <ReferenceLine y={75} stroke="#00FF99" strokeDasharray="3 3" strokeOpacity={0.5} />

                  <CartesianGrid stroke="#444" strokeOpacity={0.15} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 11, fill: "#9898a8" }}
                    tickFormatter={(v) => new Date(v as string).toLocaleDateString("it-IT", { year: "2-digit", month: "short" })}
                  />
                  <YAxis
                    domain={[0, 100]}
                    tick={{ fontSize: 11, fill: "#9898a8" }}
                    label={{ value: "Fear & Greed", angle: -90, position: "insideLeft", fill: "#9898a8", fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{ background: "#16161e", border: "1px solid #C5A059", fontSize: 12 }}
                    labelStyle={{ color: "#C5A059" }}
                    labelFormatter={(v) => formatDate(v as string)}
                    formatter={(val: number | string, name: string) => {
                      if (name === "value") return [val, "Daily"];
                      if (name === "ema") return [Number(val).toFixed(1), "EMA-24w"];
                      return [val, name];
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: "#9898a8" }} />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#C5A059"
                    strokeWidth={1}
                    fill="url(#fngArea)"
                    name="Daily F&G"
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="ema"
                    stroke="#F7931A"
                    strokeWidth={2.5}
                    dot={false}
                    name="EMA-24w (paper predictor)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
              <p className="text-xs text-[var(--foreground)]/50 mt-2">
                Zone bands: 0-24 Extreme Fear · 25-44 Fear · 45-54 Neutral · 55-74 Greed · 75-100 Extreme Greed.
                EMA-24w (linea arancione) è il predictor robusto OOS per ritorni 1-3y secondo Zhang-Watts.
              </p>
            </section>

            {/* Recent entries table */}
            <section className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
              <h2 className="text-sm uppercase tracking-wider text-[var(--gold)] mb-3">
                Recenti (ultimi 12 punti)
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-[var(--foreground)]/60 border-b border-[var(--gold)]/20">
                      <th className="py-2 pr-4">Date</th>
                      <th className="py-2 pr-4">Value</th>
                      <th className="py-2 pr-4">Classification (alternative.me)</th>
                      <th className="py-2 pr-4">EMA-24w</th>
                      <th className="py-2 pr-4">Zone</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.points.slice(-12).reverse().map((p: FngPoint) => (
                      <tr key={p.date} className="border-b border-[var(--gold)]/10">
                        <td className="py-1.5 pr-4 font-mono">{formatDate(p.date)}</td>
                        <td className="py-1.5 pr-4 font-mono text-[var(--gold)]">{p.value}</td>
                        <td className="py-1.5 pr-4">{p.classification}</td>
                        <td className="py-1.5 pr-4 font-mono">{p.ema_24w?.toFixed(1) ?? "—"}</td>
                        <td className="py-1.5 pr-4">
                          <span
                            className="px-2 py-0.5 text-[10px] uppercase tracking-wider"
                            style={{
                              color: ZONE_COLORS[p.zone] ?? "#C5A059",
                              border: `1px solid ${ZONE_COLORS[p.zone] ?? "#C5A059"}`,
                            }}
                          >
                            {ZONE_LABELS[p.zone] ?? p.zone}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function SummaryCard({
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
      <div className="text-[10px] uppercase tracking-widest text-[var(--foreground)]/50">{label}</div>
      <div className="text-2xl font-mono mt-1" style={{ color }}>
        {value}
      </div>
      {hint && <div className="text-[10px] text-[var(--foreground)]/50 mt-1">{hint}</div>}
    </div>
  );
}
