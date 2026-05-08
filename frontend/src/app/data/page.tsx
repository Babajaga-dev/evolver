"use client";

import { useEffect, useState } from "react";

import { CandlesTable } from "@/components/CandlesTable";
import { PriceChart } from "@/components/PriceChart";
import {
  ApiError,
  api,
  type CoverageRow,
  type MarketsResponse,
  type OHLCVResponse,
} from "@/lib/api";

const RANGES = [
  { label: "7 giorni", days: 7 },
  { label: "30 giorni", days: 30 },
  { label: "90 giorni", days: 90 },
  { label: "1 anno", days: 365 },
  { label: "5 anni", days: 365 * 5 },
] as const;

type RangeOption = (typeof RANGES)[number];

export default function DataPage() {
  const [markets, setMarkets] = useState<MarketsResponse | null>(null);
  const [coverage, setCoverage] = useState<CoverageRow[]>([]);
  const [symbol, setSymbol] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState<string>("4h");
  const [range, setRange] = useState<RangeOption>(RANGES[2]);

  const [data, setData] = useState<OHLCVResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Carica universe + coverage al mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [m, c] = await Promise.all([api.markets(), api.coverage()]);
        if (!cancelled) {
          setMarkets(m);
          setCoverage(c);
          // Imposta defaults dai markets se diversi
          if (m.symbols.length > 0 && !m.symbols.includes(symbol)) {
            setSymbol(m.symbols[0]);
          }
          if (m.timeframes.length > 0 && !m.timeframes.includes(timeframe)) {
            setTimeframe(m.timeframes[0]);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiError
              ? `Markets fetch failed: ${e.message}`
              : "Markets fetch failed",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Carica candele quando cambiano filtri
  useEffect(() => {
    if (!symbol || !timeframe) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const end = new Date();
    const start = new Date(end.getTime() - range.days * 24 * 3600 * 1000);
    api
      .ohlcv(symbol, timeframe, { start, end, limit: 5000, order: "asc" })
      .then((d) => {
        if (!cancelled) {
          setData(d);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Fetch failed");
          setData(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, timeframe, range]);

  const cov = coverage.find(
    (c) => c.symbol === symbol && c.timeframe === timeframe,
  );

  return (
    <main className="min-h-screen px-4 py-12 md:px-8 md:py-20">
      <div className="mx-auto max-w-6xl">
        <p className="mb-2 text-xs uppercase tracking-[0.4em] text-[--color-gold]">
          Evolver — Data Explorer
        </p>
        <h1
          className="mb-6 text-3xl md:text-5xl"
          style={{ fontFamily: "var(--font-deco)", letterSpacing: "0.08em" }}
        >
          Market Data
        </h1>
        <p className="mb-8 max-w-prose text-sm leading-relaxed text-[--color-text-secondary]">
          Storico OHLCV per gli asset dell'universe attivo. I dati arrivano
          da Binance, salvati in TimescaleDB hypertable, serviti via API.
        </p>

        {/* Filters */}
        <div className="mb-8 grid gap-4 border-y border-[--color-surface-border] py-6 md:grid-cols-3">
          <Field label="Symbol">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full rounded-none border border-[--color-surface-border] bg-[--color-surface-card] px-3 py-2 font-mono text-sm text-[--color-text-primary] focus:border-[--color-gold] focus:outline-none"
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
              className="w-full rounded-none border border-[--color-surface-border] bg-[--color-surface-card] px-3 py-2 font-mono text-sm text-[--color-text-primary] focus:border-[--color-gold] focus:outline-none"
            >
              {(markets?.timeframes ?? [timeframe]).map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Range">
            <div className="flex flex-wrap gap-1">
              {RANGES.map((r) => {
                const active = r.days === range.days;
                return (
                  <button
                    key={r.label}
                    onClick={() => setRange(r)}
                    className="border px-2 py-1 font-mono text-xs transition-colors"
                    style={{
                      borderColor: active
                        ? "var(--color-gold)"
                        : "var(--color-surface-border)",
                      color: active
                        ? "var(--color-gold)"
                        : "var(--color-text-secondary)",
                      background: active
                        ? "var(--color-surface-elevated)"
                        : "transparent",
                    }}
                  >
                    {r.label}
                  </button>
                );
              })}
            </div>
          </Field>
        </div>

        {/* Coverage strip */}
        <div className="mb-6 font-mono text-xs text-[--color-text-secondary]">
          {cov ? (
            <>
              ◆ Coverage <span className="text-[--color-gold]">{cov.symbol}</span>{" "}
              <span className="text-[--color-gold]">{cov.timeframe}</span>:{" "}
              {cov.count.toLocaleString()} candele
              {cov.first && cov.last && (
                <>
                  {" "}
                  · da {cov.first.slice(0, 10)} a {cov.last.slice(0, 10)}
                </>
              )}
            </>
          ) : (
            <span className="text-[--color-text-muted]">
              ◆ No coverage info — backfill ancora in corso?
            </span>
          )}
        </div>

        {/* Chart */}
        <section className="mb-10 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
          <h2
            className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Close price
          </h2>
          {loading ? (
            <p className="font-mono text-sm text-[--color-text-muted]">
              Loading…
            </p>
          ) : error ? (
            <p className="font-mono text-sm text-[--color-crimson]">
              ✕ {error}
            </p>
          ) : (
            <PriceChart candles={data?.candles ?? []} />
          )}
        </section>

        {/* Table */}
        <section className="mb-16 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
          <h2
            className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Recent candles {data && `· ${data.count} loaded`}
          </h2>
          {data ? (
            <CandlesTable candles={data.candles} />
          ) : (
            <p className="font-mono text-xs text-[--color-text-muted]">
              {error ?? "—"}
            </p>
          )}
        </section>

        <footer className="mt-12 text-xs text-[--color-text-muted]">
          <a
            href="/"
            className="hover:text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            ← Back to home
          </a>
        </footer>
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
