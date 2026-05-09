"use client";

import { useCallback, useEffect, useState } from "react";

import { NewsStatsCards } from "@/components/NewsStatsCards";
import { NewsTable } from "@/components/NewsTable";
import {
  ApiError,
  api,
  type NewsItem,
  type NewsStats,
} from "@/lib/api";

const ASSET_OPTIONS = ["", "BTC", "ETH", "SOL", "BNB", "XRP", "USDT"] as const;

const EVENT_TYPES = [
  "",
  "hack",
  "regulation",
  "partnership",
  "adoption",
  "technology",
  "opinion",
  "market",
  "macro",
  "other",
] as const;

export default function NewsPage() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [stats, setStats] = useState<NewsStats | null>(null);
  const [loading, setLoading] = useState(true);

  // Filters
  const [asset, setAsset] = useState<string>("");
  const [eventType, setEventType] = useState<string>("");
  const [onlyScored, setOnlyScored] = useState(true);

  // Triggers
  const [refreshing, setRefreshing] = useState(false);
  const [scoring, setScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [list, s] = await Promise.all([
        api.listNews({
          limit: 100,
          asset: asset || undefined,
          eventType: eventType || undefined,
          onlyScored,
        }),
        api.newsStats(),
      ]);
      setItems(list.items);
      setStats(s);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [asset, eventType, onlyScored]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-refresh stats ogni 30s (anche per vedere lo scoring batch progress)
  useEffect(() => {
    const interval = setInterval(() => {
      api.newsStats().then(setStats).catch(() => undefined);
    }, 30_000);
    return () => clearInterval(interval);
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const r = await api.refreshNews();
      setToast(
        `Fetch completato — ${r.fetched} totali · ${r.inserted} nuove ingestite.`,
      );
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Refresh failed");
    } finally {
      setRefreshing(false);
      setTimeout(() => setToast(null), 5000);
    }
  };

  const handleScore = async () => {
    setScoring(true);
    setError(null);
    try {
      const r = await api.scoreNewsBatch(20, 4);
      setToast(
        `Scoring batch — picked ${r.picked} · scored ${r.scored} · failed ${r.failed}.`,
      );
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Score batch failed");
    } finally {
      setScoring(false);
      setTimeout(() => setToast(null), 6000);
    }
  };

  return (
    <main className="min-h-screen px-4 py-8 md:px-8 md:py-12">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p
              className="mb-1 text-xs uppercase tracking-[0.4em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Phase 3 · News Intelligence
            </p>
            <h1
              className="text-3xl md:text-5xl"
              style={{
                fontFamily: "var(--font-deco)",
                letterSpacing: "0.08em",
              }}
            >
              The Oracle's Ledger
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[--color-text-secondary]">
              Feed RSS aggregati, classificati da Claude Haiku.
              Sentiment, event type, asset menzionati — pronti per influenzare
              il regime detector della popolazione.
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

        {/* Stats */}
        <section className="mb-6">
          <NewsStatsCards stats={stats} loading={loading} />
        </section>

        {/* Event type breakdown — sub-strip */}
        {stats && Object.keys(stats.by_event_type_24h).length > 0 && (
          <section className="mb-6 flex flex-wrap items-center gap-2 border-t border-[--color-surface-border] pt-4">
            <span
              className="text-[10px] uppercase tracking-[0.25em] text-[--color-text-muted]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              24h Event Mix:
            </span>
            {Object.entries(stats.by_event_type_24h)
              .sort((a, b) => b[1] - a[1])
              .map(([type, count]) => (
                <span
                  key={type}
                  className="border border-[--color-surface-border] px-2 py-0.5 text-xs"
                  style={{
                    fontFamily: "var(--font-mono)",
                    color: "var(--color-text-secondary)",
                  }}
                >
                  {type} <span className="text-[--color-gold]">{count}</span>
                </span>
              ))}
          </section>
        )}

        {/* Controls */}
        <section className="mb-6 grid gap-3 border-t border-[--color-surface-border] pt-4 md:grid-cols-[1fr_auto] md:items-end">
          {/* Filters */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Asset
              </span>
              <select
                value={asset}
                onChange={(e) => setAsset(e.target.value)}
                className="border border-[--color-surface-border] bg-[--color-surface-card] px-2 py-2 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {ASSET_OPTIONS.map((a) => (
                  <option key={a} value={a}>
                    {a || "all"}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Event type
              </span>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                className="border border-[--color-surface-border] bg-[--color-surface-card] px-2 py-2 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t || "all"}
                  </option>
                ))}
              </select>
            </label>

            <label className="col-span-2 flex items-center gap-2 md:col-span-1">
              <input
                type="checkbox"
                checked={onlyScored}
                onChange={(e) => setOnlyScored(e.target.checked)}
                className="accent-[--color-gold]"
              />
              <span
                className="text-xs uppercase tracking-[0.2em] text-[--color-text-secondary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Only scored
              </span>
            </label>

            <button
              type="button"
              onClick={reload}
              className="border border-[--color-surface-border] px-3 py-2 text-xs uppercase tracking-[0.2em] text-[--color-text-secondary] hover:border-[--color-gold] hover:text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Reload
            </button>
          </div>

          {/* Trigger buttons */}
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              className="border border-[--color-gold]/60 bg-transparent px-4 py-2 text-xs uppercase tracking-[0.25em] text-[--color-gold] hover:bg-[--color-gold] hover:text-[--color-void] disabled:cursor-not-allowed disabled:opacity-50"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              {refreshing ? "Fetching…" : "◆ Refresh feeds"}
            </button>
            <button
              type="button"
              onClick={handleScore}
              disabled={scoring}
              className="border border-[#f7931a] bg-[#f7931a] px-4 py-2 text-xs uppercase tracking-[0.25em] text-[--color-void] hover:bg-[#f7931a]/90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              {scoring ? "Scoring…" : "◆ Score batch"}
            </button>
          </div>
        </section>

        {/* Error / toast */}
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

        {/* Table */}
        <section>
          <NewsTable items={items} loading={loading} />
        </section>

        <footer
          className="mt-12 border-t border-[--color-surface-border] pt-4 text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          Sources: CoinDesk · Cointelegraph · The Block · Decrypt · Bitcoinist
          {" · "}
          Scoring model: claude-haiku-4-5
        </footer>
      </div>
    </main>
  );
}
