"use client";

import { useEffect, useState } from "react";

interface HealthResponse {
  status: "ok" | "degraded";
  database: boolean;
  timescale: boolean;
  redis: boolean;
}

// Chiamata diretta cross-origin al backend pubblico — bypass del
// rewrite Next.js, che con la rete external `dokploy-network` non
// risolve il service alias `backend`. CORS è gestito lato FastAPI
// via API_CORS_ORIGINS (deve includere http://evolve.lan).
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://api.evolve.lan";

export function HealthBadge() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchHealth = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: HealthResponse = await res.json();
        if (!cancelled) {
          setHealth(data);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "unknown error");
          setHealth(null);
        }
      }
    };
    fetchHealth();
    const interval = setInterval(fetchHealth, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (error) {
    return (
      <div className="font-mono text-sm text-[--color-crimson]">
        ✕ Backend unreachable — {error}
      </div>
    );
  }

  if (!health) {
    return (
      <div className="font-mono text-sm text-[--color-text-muted]">
        Checking…
      </div>
    );
  }

  const overallColor =
    health.status === "ok" ? "var(--color-gold)" : "var(--color-crimson)";

  return (
    <div className="space-y-1 font-mono text-sm">
      <div className="flex items-baseline gap-3">
        <span style={{ color: overallColor }}>●</span>
        <span style={{ color: overallColor }}>{health.status.toUpperCase()}</span>
      </div>
      <ul className="ml-5 mt-2 space-y-0.5 text-xs text-[--color-text-secondary]">
        <li>
          database: <Status ok={health.database} />
        </li>
        <li>
          timescaledb: <Status ok={health.timescale} />
        </li>
        <li>
          redis: <Status ok={health.redis} />
        </li>
      </ul>
    </div>
  );
}

function Status({ ok }: { ok: boolean }) {
  return (
    <span style={{ color: ok ? "var(--color-gold)" : "var(--color-crimson)" }}>
      {ok ? "✓" : "✕"}
    </span>
  );
}
