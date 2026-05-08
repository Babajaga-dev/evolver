/**
 * Client TS verso il backend Evolver.
 *
 * Usa NEXT_PUBLIC_BACKEND_URL (build-time inline) con default
 * `http://api.evolve.lan` per chiamate cross-origin dal browser.
 */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://api.evolve.lan";

// ---------------------------------------------------------------------------
// Types — mirror dei Pydantic schemas
// ---------------------------------------------------------------------------

export interface OHLCVCandle {
  timestamp: string; // ISO 8601
  symbol: string;
  timeframe: string;
  open: string; // Decimal as string
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface OHLCVResponse {
  symbol: string;
  timeframe: string;
  count: number;
  candles: OHLCVCandle[];
}

export interface MarketsResponse {
  symbols: string[];
  timeframes: string[];
}

export interface CoverageRow {
  symbol: string;
  timeframe: string;
  count: number;
  first: string | null;
  last: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  database: boolean;
  timescale: boolean;
  redis: boolean;
}

// ---------------------------------------------------------------------------
// Indicators
// ---------------------------------------------------------------------------

export interface IndicatorParamInfo {
  name: string;
  type: "int" | "float" | "str";
  default: number | string;
  min?: number | null;
  max?: number | null;
  choices?: string[] | null;
  description?: string;
}

export interface IndicatorInfo {
  id: string;
  label: string;
  kind: "overlay" | "panel";
  description: string;
  params: IndicatorParamInfo[];
  output_keys: string[];
}

export interface IndicatorsRegistryResponse {
  indicators: IndicatorInfo[];
}

export interface IndicatorPoint {
  timestamp: string;
  values: Record<string, number | null>;
}

export interface IndicatorResponse {
  symbol: string;
  timeframe: string;
  indicator: string;
  params: Record<string, number | string>;
  output_keys: string[];
  count: number;
  points: IndicatorPoint[];
  label: string;
  kind: "overlay" | "panel";
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  const res = await fetch(url, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  health: () => fetchJson<HealthResponse>("/health"),

  markets: () => fetchJson<MarketsResponse>("/api/v1/markets"),

  coverage: () => fetchJson<CoverageRow[]>("/api/v1/coverage"),

  ohlcv: (
    symbol: string,
    timeframe: string,
    opts: {
      start?: Date;
      end?: Date;
      limit?: number;
      order?: "asc" | "desc";
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.start) params.set("start", opts.start.toISOString());
    if (opts.end) params.set("end", opts.end.toISOString());
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.order) params.set("order", opts.order);

    const qs = params.toString();
    const path = `/api/v1/ohlcv/${encodeURIComponent(symbol)}/${timeframe}${
      qs ? `?${qs}` : ""
    }`;
    return fetchJson<OHLCVResponse>(path);
  },

  indicatorsRegistry: () =>
    fetchJson<IndicatorsRegistryResponse>("/api/v1/indicators"),

  indicator: (
    symbol: string,
    timeframe: string,
    indicator: string,
    indicatorParams: Record<string, number | string> = {},
    opts: { start?: Date; end?: Date; limit?: number } = {},
  ) => {
    const params = new URLSearchParams();
    params.set("indicator", indicator);
    if (opts.start) params.set("start", opts.start.toISOString());
    if (opts.end) params.set("end", opts.end.toISOString());
    if (opts.limit) params.set("limit", String(opts.limit));
    for (const [key, value] of Object.entries(indicatorParams)) {
      params.set(key, String(value));
    }
    const path = `/api/v1/indicators/${encodeURIComponent(symbol)}/${timeframe}?${params.toString()}`;
    return fetchJson<IndicatorResponse>(path);
  },
};

export { ApiError };
