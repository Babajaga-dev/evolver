"use client";

import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  api,
  type CleanupResult,
  type CleanupTarget,
  type MaintenanceStats,
  type SchedulerJob,
  type SystemSetting,
} from "@/lib/api";

interface CleanupSpec {
  target: CleanupTarget;
  label: string;
  description: string;
  supportsAge: boolean;
  destructive: boolean;
}

const CLEANUP_SPECS: CleanupSpec[] = [
  {
    target: "news_scored_all",
    label: "Re-score news",
    description: "Cancella tutti gli scoring LLM. Le news raw restano, vanno ri-scorate.",
    supportsAge: false,
    destructive: true,
  },
  {
    target: "news_raw_old",
    label: "Purge news vecchie",
    description: "Elimina news più vecchie di N giorni (cascade su scored).",
    supportsAge: true,
    destructive: true,
  },
  {
    target: "ohlcv_old",
    label: "Purge OHLCV vecchie",
    description: "Elimina candele oltre N giorni — TimescaleDB le aveva già compresse.",
    supportsAge: true,
    destructive: true,
  },
  {
    target: "ga_runs_failed",
    label: "Purge GA runs falliti",
    description: "Cancella dal Redis i run con status=failed.",
    supportsAge: false,
    destructive: false,
  },
  {
    target: "ga_runs_completed",
    label: "Purge GA runs completati",
    description: "Cancella dal Redis i run con status=completed.",
    supportsAge: false,
    destructive: false,
  },
  {
    target: "ga_runs_all",
    label: "Purge tutti i GA runs",
    description: "Wipe completo dello stato GA su Redis (esclusi i running).",
    supportsAge: false,
    destructive: true,
  },
];

export default function ControlPage() {
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [jobs, setJobs] = useState<SchedulerJob[]>([]);
  const [stats, setStats] = useState<MaintenanceStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const [s, j, st] = await Promise.all([
        api.systemSettings(),
        api.systemJobs(),
        api.maintenanceStats(),
      ]);
      setSettings(s.settings);
      setJobs(j.jobs);
      setStats(st);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-refresh ogni 15s per vedere i job last_run aggiornarsi
  useEffect(() => {
    const interval = setInterval(() => {
      Promise.all([api.systemJobs(), api.maintenanceStats()])
        .then(([j, st]) => {
          setJobs(j.jobs);
          setStats(st);
        })
        .catch(() => undefined);
    }, 15_000);
    return () => clearInterval(interval);
  }, []);

  const flashToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 5000);
  };

  return (
    <main className="min-h-screen px-4 py-8 md:px-8 md:py-12">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p
              className="mb-1 text-xs uppercase tracking-[0.4em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              System · Control Panel
            </p>
            <h1
              className="text-3xl md:text-5xl"
              style={{
                fontFamily: "var(--font-deco)",
                letterSpacing: "0.08em",
              }}
            >
              The Keeper's Sanctum
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[--color-text-secondary]">
              Pannello unico per automatismi, manutenzione database, stato
              dello scheduler. Toggle per ogni feature, dry-run di default
              sulle pulizie distruttive.
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

        {loading && (
          <div className="font-mono text-sm text-[--color-text-muted]">
            Caricando lo stato del sistema...
          </div>
        )}

        {/* Section 1 — Automation */}
        <section className="mb-12">
          <SectionHeader
            label="01 · Automation"
            title="Automatismi e schedulers"
            blurb="Toggle per i job ricorrenti. Ogni job rilegge il flag a ogni tick — toggle prende effetto al successivo intervallo."
          />
          <div className="grid gap-3">
            {settings
              .filter((s) => s.category === "automation")
              .map((s) => (
                <SettingCard
                  key={s.key}
                  setting={s}
                  job={jobs.find((j) => j.id === s.key)}
                  onChange={async (next) => {
                    try {
                      await api.updateSystemSetting(s.key, next);
                      await reload();
                      flashToast(`Setting ${s.key} aggiornato.`);
                    } catch (e) {
                      setError(
                        e instanceof ApiError ? e.message : "Update failed",
                      );
                    }
                  }}
                  onRunNow={async () => {
                    try {
                      flashToast(`Esecuzione ${s.key} avviata...`);
                      const r = await api.runSystemJob(s.key);
                      await reload();
                      flashToast(`${r.message}`);
                    } catch (e) {
                      setError(
                        e instanceof ApiError ? e.message : "Run failed",
                      );
                    }
                  }}
                />
              ))}
          </div>
        </section>

        {/* Section 2 — Database stats + cleanup */}
        <section className="mb-12">
          <SectionHeader
            label="02 · Database"
            title="Stato e manutenzione"
            blurb="Conteggi per tabella. Le pulizie distruttive girano in dry-run di default — clicca due volte per confermare."
          />
          <DatabaseStats stats={stats} />
          <div className="mt-6 grid gap-3">
            {CLEANUP_SPECS.map((spec) => (
              <CleanupCard
                key={spec.target}
                spec={spec}
                onResult={(r) => {
                  if (r.dry_run) {
                    flashToast(
                      `Dry-run ${spec.target}: ${r.details.candidates ?? r.deleted} candidati`,
                    );
                  } else {
                    flashToast(
                      `${spec.target} eseguito — ${r.deleted} righe rimosse.`,
                    );
                    reload();
                  }
                }}
                onError={(msg) => setError(msg)}
              />
            ))}
          </div>
        </section>

        {/* Section 3 — Scheduler jobs */}
        <section className="mb-12">
          <SectionHeader
            label="03 · Scheduler"
            title="Stato dei job APScheduler"
            blurb="Snapshot di tutti i job. Last run + status + next trigger."
          />
          <JobsTable jobs={jobs} />
        </section>

        <footer
          className="mt-12 border-t border-[--color-surface-border] pt-4 text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          Auto-refresh ogni 15s. Tutte le scritture loggate su backend.
        </footer>
      </div>
    </main>
  );
}

// ===========================================================================
// Section header
// ===========================================================================

function SectionHeader({
  label,
  title,
  blurb,
}: {
  label: string;
  title: string;
  blurb: string;
}) {
  return (
    <div className="mb-4 border-b border-[--color-surface-border] pb-3">
      <p
        className="text-[10px] uppercase tracking-[0.4em] text-[--color-gold]"
        style={{ fontFamily: "var(--font-serif)" }}
      >
        {label}
      </p>
      <h2
        className="mt-1 text-xl md:text-2xl"
        style={{ fontFamily: "var(--font-serif)", letterSpacing: "0.05em" }}
      >
        {title}
      </h2>
      <p className="mt-1 max-w-2xl text-xs text-[--color-text-secondary]">
        {blurb}
      </p>
    </div>
  );
}

// ===========================================================================
// Setting card — toggle + numeric inputs
// ===========================================================================

function SettingCard({
  setting,
  job,
  onChange,
  onRunNow,
}: {
  setting: SystemSetting;
  job?: SchedulerJob;
  onChange: (next: Record<string, unknown>) => void;
  onRunNow: () => void;
}) {
  const enabled = Boolean(setting.value.enabled);

  return (
    <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p
            className="font-mono text-sm text-[--color-text-primary]"
            style={{ letterSpacing: "0.05em" }}
          >
            {setting.key}
          </p>
          {setting.description && (
            <p className="mt-1 text-xs text-[--color-text-secondary]">
              {setting.description}
            </p>
          )}
          {job && (
            <p className="mt-2 text-[10px] text-[--color-text-muted] font-mono">
              {job.last_run_at ? (
                <>
                  Last run: {new Date(job.last_run_at).toLocaleTimeString()} ·{" "}
                  <span
                    style={{
                      color:
                        job.last_status === "ok"
                          ? "#00ff99"
                          : job.last_status === "error"
                            ? "#e63946"
                            : "var(--color-text-muted)",
                    }}
                  >
                    {job.last_status}
                  </span>
                  {job.last_message ? ` — ${job.last_message}` : ""}
                </>
              ) : (
                "Mai eseguito"
              )}
              {job.next_run && (
                <> · Next: {new Date(job.next_run).toLocaleTimeString()}</>
              )}
            </p>
          )}
        </div>

        <Toggle
          checked={enabled}
          onChange={(next) =>
            onChange({ ...setting.value, enabled: next })
          }
        />
      </div>

      {/* Numeric inputs per gli altri campi value */}
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {Object.entries(setting.value)
          .filter(([k]) => k !== "enabled")
          .map(([k, v]) => (
            <label key={k} className="flex flex-col gap-1">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-muted]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                {k}
              </span>
              <input
                type="number"
                defaultValue={String(v)}
                onBlur={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isFinite(n)) return;
                  if (n === Number(v)) return;
                  onChange({ ...setting.value, [k]: n });
                }}
                className="border border-[--color-surface-border] bg-[--color-surface-elevated] px-2 py-1 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              />
            </label>
          ))}
      </div>

      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={onRunNow}
          className="border border-[--color-gold]/60 bg-transparent px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-[--color-gold] hover:bg-[--color-gold] hover:text-[--color-surface]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          ◆ Run now
        </button>
      </div>
    </div>
  );
}

// ===========================================================================
// Toggle
// ===========================================================================

function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="relative h-7 w-14 border transition-colors"
      style={{
        backgroundColor: checked ? "#f7931a" : "var(--color-surface-elevated)",
        borderColor: checked
          ? "#f7931a"
          : "var(--color-surface-border)",
      }}
    >
      <span
        className="absolute top-0.5 h-5 w-5 transition-all"
        style={{
          left: checked ? "calc(100% - 22px)" : "2px",
          backgroundColor: checked ? "#080210" : "var(--color-text-muted)",
        }}
      />
    </button>
  );
}

// ===========================================================================
// Database stats grid
// ===========================================================================

function DatabaseStats({ stats }: { stats: MaintenanceStats | null }) {
  if (!stats) {
    return (
      <div className="font-mono text-sm text-[--color-text-muted]">—</div>
    );
  }
  const cards = [
    { label: "OHLCV candles", value: stats.ohlcv.count },
    { label: "News raw", value: stats.news.raw },
    { label: "News scored", value: stats.news.scored },
    { label: "News pending", value: stats.news.pending },
    { label: "GA Postgres pop.", value: stats.ga_postgres.populations },
    { label: "GA Postgres strat.", value: stats.ga_postgres.strategies },
    { label: "GA Redis runs", value: stats.ga_redis.total },
    {
      label: "Fitness eval.",
      value: stats.ga_postgres.fitness_evaluations,
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {cards.map((c) => (
        <div
          key={c.label}
          className="border border-[--color-surface-border] bg-[--color-surface-card] px-3 py-2"
        >
          <p
            className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            {c.label}
          </p>
          <p
            className="mt-1 text-xl text-[--color-gold]"
            style={{
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.05em",
            }}
          >
            {new Intl.NumberFormat("en-US").format(c.value)}
          </p>
        </div>
      ))}
    </div>
  );
}

// ===========================================================================
// Cleanup card — dry-run, confirm
// ===========================================================================

function CleanupCard({
  spec,
  onResult,
  onError,
}: {
  spec: CleanupSpec;
  onResult: (r: CleanupResult) => void;
  onError: (msg: string) => void;
}) {
  const [olderThanDays, setOlderThanDays] = useState(
    spec.target === "ohlcv_old" ? 365 : 30,
  );
  const [running, setRunning] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<CleanupResult | null>(
    null,
  );

  const callDryRun = async () => {
    setRunning(true);
    try {
      const r = await api.cleanup(spec.target, {
        olderThanDays: spec.supportsAge ? olderThanDays : undefined,
        confirm: false,
      });
      setPendingConfirm(r);
      onResult(r);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Cleanup failed");
    } finally {
      setRunning(false);
    }
  };

  const callConfirm = async () => {
    setRunning(true);
    try {
      const r = await api.cleanup(spec.target, {
        olderThanDays: spec.supportsAge ? olderThanDays : undefined,
        confirm: true,
      });
      onResult(r);
      setPendingConfirm(null);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : "Cleanup failed");
    } finally {
      setRunning(false);
    }
  };

  const candidates = pendingConfirm
    ? Number(pendingConfirm.details.candidates ?? 0)
    : null;

  return (
    <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p
            className="font-mono text-sm text-[--color-text-primary]"
            style={{ letterSpacing: "0.05em" }}
          >
            {spec.label}
            {spec.destructive && (
              <span
                className="ml-2 text-[10px] uppercase tracking-[0.2em] text-[--color-crimson]"
                style={{
                  fontFamily: "var(--font-serif)",
                  color: "#e63946",
                }}
              >
                · destructive
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-[--color-text-secondary]">
            {spec.description}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {spec.supportsAge && (
            <label className="flex items-center gap-2">
              <span
                className="text-[10px] uppercase tracking-[0.2em] text-[--color-text-muted]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Older than (days)
              </span>
              <input
                type="number"
                value={olderThanDays}
                onChange={(e) => setOlderThanDays(Number(e.target.value))}
                min={1}
                max={3650}
                className="w-20 border border-[--color-surface-border] bg-[--color-surface-elevated] px-2 py-1 text-sm text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-mono)" }}
              />
            </label>
          )}

          {!pendingConfirm && (
            <button
              type="button"
              onClick={callDryRun}
              disabled={running}
              className="border border-[--color-surface-border] px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-[--color-text-secondary] hover:border-[--color-gold] hover:text-[--color-gold] disabled:opacity-50"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              {running ? "..." : "Dry-run"}
            </button>
          )}

          {pendingConfirm && (
            <>
              <span
                className="text-xs text-[--color-text-muted]"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {candidates ?? 0} candidati
              </span>
              <button
                type="button"
                onClick={() => setPendingConfirm(null)}
                className="border border-[--color-surface-border] px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-[--color-text-secondary] hover:text-[--color-text-primary]"
                style={{ fontFamily: "var(--font-serif)" }}
              >
                Annulla
              </button>
              <button
                type="button"
                onClick={callConfirm}
                disabled={running}
                className="border border-[--color-crimson] bg-[--color-crimson] px-3 py-1.5 text-xs uppercase tracking-[0.2em] text-[--color-warm-white] hover:bg-[--color-crimson]/80 disabled:opacity-50"
                style={{
                  fontFamily: "var(--font-serif)",
                  background: "#8b1a1a",
                  color: "#f0ede8",
                }}
              >
                {running ? "Eseguendo..." : "Conferma delete"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ===========================================================================
// Jobs table
// ===========================================================================

function JobsTable({ jobs }: { jobs: SchedulerJob[] }) {
  if (jobs.length === 0) {
    return (
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-4 font-mono text-sm text-[--color-text-muted]">
        Nessun job registrato — scheduler non ancora avviato?
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
            <th className="px-3 py-2">Job</th>
            <th className="px-3 py-2">Trigger</th>
            <th className="px-3 py-2">Next</th>
            <th className="px-3 py-2">Last</th>
            <th className="px-3 py-2">Status</th>
            <th className="px-3 py-2">Message</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr
              key={j.id}
              className="border-b border-[--color-surface-border]/40 text-[--color-text-secondary]"
            >
              <td className="px-3 py-2 text-[--color-text-primary]">{j.id}</td>
              <td className="px-3 py-2 text-[--color-text-muted]">
                {j.trigger}
              </td>
              <td className="px-3 py-2">
                {j.next_run
                  ? new Date(j.next_run).toLocaleTimeString()
                  : "—"}
              </td>
              <td className="px-3 py-2">
                {j.last_run_at
                  ? new Date(j.last_run_at).toLocaleTimeString()
                  : "—"}
              </td>
              <td
                className="px-3 py-2"
                style={{
                  color:
                    j.last_status === "ok"
                      ? "#00ff99"
                      : j.last_status === "error"
                        ? "#e63946"
                        : "var(--color-text-muted)",
                }}
              >
                {j.last_status ?? "—"}
              </td>
              <td className="px-3 py-2 text-[--color-text-muted]">
                {j.last_message ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
