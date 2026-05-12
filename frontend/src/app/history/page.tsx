"use client";

/**
 * /history — Gestione dati storici universe top-150
 *
 * Pattern UX:
 * - 4 status cards (universe total, fresh, partial, missing)
 * - Filter/search bar + timeframe selector
 * - Sortable table: simbolo, count, first, last, gap, status, action
 * - Bulk "Fill all missing" button (smart: skip fresh)
 * - Per-row "Update" button (smart: incremental from last_bar+1)
 * - Auto-refresh ogni 15s durante backfill attivo
 *
 * Smart backfill: skip simboli con gap < 1 giorno, altrimenti incremental.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { api, type SymbolStatus, type UniverseStatusResponse } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  fresh: "#00FF99",
  stale: "#C5A059",
  partial: "#F7931A",
  missing: "#8B1A1A",
};

const STATUS_LABEL: Record<string, string> = {
  fresh: "FRESH",
  stale: "STALE",
  partial: "PARTIAL",
  missing: "MISSING",
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", { year: "2-digit", month: "short", day: "2-digit" });
}

export default function HistoryPage() {
  const [data, setData] = useState<UniverseStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState("1d");
  const [filter, setFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [runningSyms, setRunningSyms] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<"symbol" | "count" | "last" | "gap_days" | "status">("status");
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const d = await api.getUniverseStatus(timeframe);
      setData(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Errore caricamento universe");
    } finally {
      setLoading(false);
    }
  }, [timeframe]);

  useEffect(() => {
    setLoading(true);
    void fetchData();
  }, [fetchData]);

  // Auto-refresh every 15s when bulk or row backfills running
  useEffect(() => {
    if (!autoRefresh) return;
    if (!bulkRunning && runningSyms.size === 0) return;
    const id = setInterval(() => void fetchData(), 15000);
    return () => clearInterval(id);
  }, [autoRefresh, bulkRunning, runningSyms, fetchData]);

  const triggerBulkBackfill = useCallback(async () => {
    try {
      setBulkRunning(true);
      setBulkMessage(null);
      const r = await api.bulkBackfillUniverse({ timeframe, only_missing: true, max_concurrent: 5 });
      setBulkMessage(`${r.message} (${r.symbols.length} symbols queued)`);
      setTimeout(() => void fetchData(), 5000);
    } catch (e) {
      setBulkMessage(e instanceof Error ? e.message : "Errore bulk backfill");
    } finally {
      setBulkRunning(false);
    }
  }, [timeframe, fetchData]);

  const triggerSmart = useCallback(async (symbol: string) => {
    try {
      setRunningSyms((s) => new Set([...Array.from(s), symbol]));
      const r = await api.smartBackfill({ symbol, timeframe });
      if (r.reason === "already_fresh") {
        setRunningSyms((s) => {
          const n = new Set(Array.from(s));
          n.delete(symbol);
          return n;
        });
        return;
      }
      // remove after refresh
      setTimeout(() => {
        void fetchData();
        setRunningSyms((s) => {
          const n = new Set(Array.from(s));
          n.delete(symbol);
          return n;
        });
      }, 15000);
    } catch (e) {
      setRunningSyms((s) => {
        const n = new Set(Array.from(s));
        n.delete(symbol);
        return n;
      });
    }
  }, [timeframe, fetchData]);

  const filteredSorted = useMemo<SymbolStatus[]>(() => {
    if (!data) return [];
    let rows = data.rows;
    if (filter) {
      const f = filter.toUpperCase();
      rows = rows.filter((r) => r.symbol.includes(f));
    }
    if (statusFilter !== "all") {
      rows = rows.filter((r) => r.status === statusFilter);
    }
    const sorted = [...rows];
    sorted.sort((a, b) => {
      let av: string | number = "";
      let bv: string | number = "";
      if (sortKey === "symbol") { av = a.symbol; bv = b.symbol; }
      else if (sortKey === "count") { av = a.count; bv = b.count; }
      else if (sortKey === "gap_days") { av = a.gap_days; bv = b.gap_days; }
      else if (sortKey === "last") { av = a.last || ""; bv = b.last || ""; }
      else if (sortKey === "status") {
        const ord = { missing: 0, partial: 1, stale: 2, fresh: 3 };
        av = ord[a.status as keyof typeof ord] ?? 4;
        bv = ord[b.status as keyof typeof ord] ?? 4;
      }
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av).localeCompare(String(bv));
    });
    return sorted;
  }, [data, filter, statusFilter, sortKey]);

  const pct = data ? (data.completed / data.total_universe) * 100 : 0;

  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)] p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="border-b border-[var(--gold)]/30 pb-4">
          <h1 className="text-3xl font-bold tracking-wider text-[var(--gold)] uppercase">
            History · Data Management
          </h1>
          <p className="text-sm text-[var(--foreground)]/60 mt-1">
            Universe top-150 USDT spot. Backfill smart (incrementale da last bar). Refresh auto durante operazioni.
          </p>
        </header>

        {/* Status cards */}
        {data && (
          <section className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <Card label="Universe" value={`${data.total_universe}`} hint="Top-150 USDT" />
            <Card label="Fresh" value={`${data.completed}`} hint={`${pct.toFixed(0)}% complete`} color={STATUS_COLOR.fresh} />
            <Card label="Partial/Stale" value={`${data.partial}`} hint="needs update" color={STATUS_COLOR.partial} />
            <Card label="Missing" value={`${data.missing}`} hint="never fetched" color={STATUS_COLOR.missing} />
            <Card label="Timeframe" value={timeframe} hint="current view" />
          </section>
        )}

        {/* Progress bar */}
        {data && (
          <div className="border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
            <div className="flex justify-between items-center mb-2 text-xs uppercase tracking-wider">
              <span className="text-[var(--gold)]">Universe completeness</span>
              <span className="font-mono">{pct.toFixed(1)}% ({data.completed}/{data.total_universe})</span>
            </div>
            <div className="h-2 bg-[#1e1e2a] rounded overflow-hidden">
              <div className="h-full transition-all duration-500" style={{ width: `${pct}%`, background: "linear-gradient(90deg, #C5A059, #F7931A)" }} />
            </div>
          </div>
        )}

        {/* Controls */}
        <section className="flex flex-wrap gap-3 items-end border border-[var(--gold)]/30 rounded p-4 bg-[var(--surface-card)]">
          <Field label="Timeframe">
            <select value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="form-input">
              <option value="1d">1d</option>
              <option value="4h">4h</option>
              <option value="1h">1h</option>
            </select>
          </Field>
          <Field label="Search symbol">
            <input type="text" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="BTC, ETH..." className="form-input" />
          </Field>
          <Field label="Status filter">
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="form-input">
              <option value="all">All</option>
              <option value="fresh">Fresh</option>
              <option value="stale">Stale</option>
              <option value="partial">Partial</option>
              <option value="missing">Missing</option>
            </select>
          </Field>
          <Field label="Sort by">
            <select value={sortKey} onChange={(e) => setSortKey(e.target.value as typeof sortKey)} className="form-input">
              <option value="status">Status</option>
              <option value="symbol">Symbol</option>
              <option value="count">Count</option>
              <option value="last">Last bar</option>
              <option value="gap_days">Gap days</option>
            </select>
          </Field>
          <div className="ml-auto flex gap-2">
            <button type="button" onClick={() => { setLoading(true); void fetchData(); }}
              className="px-3 py-2 border border-[var(--gold)]/50 text-[var(--gold)] uppercase text-xs tracking-wider hover:bg-[var(--gold)] hover:text-[var(--background)]">
              ⟲ Refresh
            </button>
            <button type="button" onClick={triggerBulkBackfill} disabled={bulkRunning || !data || data.missing + data.partial === 0}
              className="px-4 py-2 border-2 border-[var(--btc)] bg-[var(--btc)]/10 text-[var(--btc)] uppercase tracking-wider text-xs font-semibold hover:bg-[var(--btc)] hover:text-[var(--background)] disabled:opacity-40">
              {bulkRunning ? "Triggering..." : `◆ Fill all missing (${data ? data.missing + data.partial : 0})`}
            </button>
          </div>
        </section>

        {bulkMessage && (
          <div className="px-4 py-2 border border-[var(--gold)]/40 bg-[var(--gold)]/5 rounded text-xs">
            {bulkMessage}
          </div>
        )}

        {error && (
          <div className="p-4 border border-[#8B1A1A] bg-[#8B1A1A]/10 rounded text-[#FF6666] text-sm">
            {error}
          </div>
        )}

        {/* Table */}
        {loading && !data ? (
          <div className="p-8 text-center text-[var(--foreground)]/60">Caricamento universe...</div>
        ) : (
          <section className="border border-[var(--gold)]/30 rounded bg-[var(--surface-card)] overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-[var(--surface-elevated)]">
                  <tr className="text-left text-[var(--foreground)]/60 uppercase tracking-wider text-[10px]">
                    <th className="py-2 px-3">Symbol</th>
                    <th className="py-2 px-3 text-right">Count</th>
                    <th className="py-2 px-3">First</th>
                    <th className="py-2 px-3">Last</th>
                    <th className="py-2 px-3 text-right">Gap</th>
                    <th className="py-2 px-3">Status</th>
                    <th className="py-2 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSorted.map((r) => (
                    <tr key={r.symbol} className="border-t border-[var(--gold)]/10 hover:bg-[var(--surface-elevated)]/50">
                      <td className="py-1.5 px-3 font-mono text-[var(--gold)]">{r.symbol}</td>
                      <td className="py-1.5 px-3 text-right font-mono">{r.count.toLocaleString("it-IT")}</td>
                      <td className="py-1.5 px-3 font-mono">{fmtDate(r.first)}</td>
                      <td className="py-1.5 px-3 font-mono">{fmtDate(r.last)}</td>
                      <td className="py-1.5 px-3 text-right font-mono">{r.gap_days.toFixed(1)}d</td>
                      <td className="py-1.5 px-3">
                        <span className="px-2 py-0.5 text-[10px] uppercase tracking-wider"
                          style={{ color: STATUS_COLOR[r.status] ?? "#C5A059", border: `1px solid ${STATUS_COLOR[r.status] ?? "#C5A059"}` }}>
                          {STATUS_LABEL[r.status] ?? r.status}
                        </span>
                      </td>
                      <td className="py-1.5 px-3 text-right">
                        <button type="button" onClick={() => triggerSmart(r.symbol)}
                          disabled={r.status === "fresh" || runningSyms.has(r.symbol)}
                          className="px-2 py-1 text-[10px] uppercase border border-[var(--gold)]/40 text-[var(--gold)] hover:bg-[var(--gold)] hover:text-[var(--background)] disabled:opacity-30 disabled:cursor-not-allowed">
                          {runningSyms.has(r.symbol) ? "..." : r.status === "fresh" ? "OK" : "Update"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-2 text-[10px] text-[var(--foreground)]/50 border-t border-[var(--gold)]/10">
              Showing {filteredSorted.length} of {data?.rows.length ?? 0} symbols · Auto-refresh ogni 15s durante backfill
            </div>
          </section>
        )}
      </div>

      <style jsx>{`
        :global(.form-input) {
          background: #1e1e2a;
          color: #e4e4ef;
          border: 1px solid #C5A059;
          padding: 6px 8px;
          font-size: 11px;
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
      <div className="text-2xl font-mono mt-1" style={{ color }}>{value}</div>
      {hint && <div className="text-[10px] text-[var(--foreground)]/50 mt-1">{hint}</div>}
    </div>
  );
}
