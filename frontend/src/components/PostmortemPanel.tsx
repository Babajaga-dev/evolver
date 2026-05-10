"use client";

import { useState } from "react";

import { ApiError, api, type PostmortemResponse } from "@/lib/api";

/**
 * Pannello Postmortem Opus — generazione manuale del review settimanale.
 *
 * Costo stimato per chiamata: ~$0.50-1.00 (Opus 4.6, ~30k tok input, ~3k output).
 * UI mostra warning costo prima del trigger, e renderizza il markdown
 * risultante in un block stile manoscritto.
 */
export function PostmortemPanel() {
  const [days, setDays] = useState(7);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<PostmortemResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setRunning(true);
    setError(null);
    try {
      const r = await api.postmortemGenerate(days);
      setReport(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Postmortem failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <section className="mb-12">
      <div className="mb-4 border-b border-[--color-surface-border] pb-3">
        <p
          className="text-[10px] uppercase tracking-[0.4em] text-[--color-gold]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          04 · Weekly Review
        </p>
        <h2
          className="mt-1 text-xl md:text-2xl"
          style={{ fontFamily: "var(--font-serif)", letterSpacing: "0.05em" }}
        >
          Postmortem · Claude Opus
        </h2>
        <p className="mt-1 max-w-2xl text-xs text-[--color-text-secondary]">
          Genera un review qualitativo settimanale: top strategies + news
          regime + paper P&L → Opus produce markdown analitico.
          Costo stimato $0.50–1.00 per chiamata.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1">
          <span
            className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-muted]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Period (days)
          </span>
          <input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-24 border border-[--color-surface-border] bg-[--color-surface-elevated] px-2 py-1.5 text-sm text-[--color-text-primary]"
            style={{ fontFamily: "var(--font-mono)" }}
          />
        </label>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={running}
          className="px-4 py-2 text-xs uppercase tracking-[0.25em]"
          style={{
            fontFamily: "var(--font-serif)",
            background: running ? "var(--color-surface-elevated)" : "#f7931a",
            color: running ? "var(--color-text-muted)" : "var(--color-void)",
            border: "1px solid #f7931a",
            cursor: running ? "wait" : "pointer",
          }}
        >
          {running ? "Generating… (Opus runs ~30s)" : "◆ Generate Postmortem"}
        </button>
      </div>

      {error && (
        <div
          className="mt-4 border border-[--color-crimson] bg-[--color-crimson]/10 px-4 py-2 text-sm"
          style={{ color: "var(--color-crimson, #e63946)" }}
        >
          {error}
        </div>
      )}

      {report && (
        <article
          className="mt-6 border border-[--color-gold]/40 bg-[--color-surface-card] px-6 py-6"
          style={{ fontFamily: "var(--font-body, var(--font-serif))" }}
        >
          <header
            className="mb-4 flex flex-wrap items-baseline justify-between gap-2 border-b border-[--color-surface-border] pb-3 text-[11px]"
            style={{
              fontFamily: "var(--font-mono)",
              color: "var(--color-text-muted)",
            }}
          >
            <span>
              {new Date(report.period_start).toLocaleDateString()} →{" "}
              {new Date(report.period_end).toLocaleDateString()}
            </span>
            <span>
              {report.model} · in:{report.tokens_input} out:{report.tokens_output} ·
              ~${report.cost_usd_estimate.toFixed(4)}
            </span>
          </header>
          <div
            className="whitespace-pre-wrap text-sm leading-relaxed text-[--color-text-primary]"
            style={{ lineHeight: 1.7 }}
          >
            {report.markdown}
          </div>
        </article>
      )}
    </section>
  );
}
