/**
 * API client per Evolver backend.
 *
 * Tutto type-safe, no `any`. Errori wrappati in ApiError per gestione UI.
 *
 * NEXT_PUBLIC_BACKEND_URL deve essere build-inlinato (Next.js public env).
 */

export const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://api.evolve.lan";

export class ApiError extends Error {
  public status: number;
  public body: unknown;
  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BACKEND_URL}${path}`;
  const res = await fetch(url, init);
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const msg =
      body && typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `HTTP ${res.status}: ${res.statusText}`;
    throw new ApiError(msg, res.status, body);
  }
  return body as T;
}

// ---------------------------------------------------------------------------
// OHLCV / Markets
// ---------------------------------------------------------------------------

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OHLCVResponse {
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  count: number;
  candles: Candle[];
}

export interface MarketInfo {
  symbol: string;
  timeframes: string[];
}

export interface MarketsResponse {
  markets: MarketInfo[];
}

export interface CoverageRow {
  symbol: string;
  timeframe: string;
  count: number;
  oldest: string | null;
  newest: string | null;
}

// ---------------------------------------------------------------------------
// Indicators
// ---------------------------------------------------------------------------

export interface IndicatorParam {
  name: string;
  type: string;
  default: number | string | null;
  min: number | null;
  max: number | null;
  description: string | null;
}

export interface IndicatorInfo {
  id: string;
  family: string;
  description: string;
  params: IndicatorParam[];
  output_keys: string[];
}

export interface IndicatorSeriesPoint {
  timestamp: string;
  values: Record<string, number | null>;
}

export interface IndicatorResponse {
  symbol: string;
  timeframe: string;
  indicator: string;
  params: Record<string, number | string>;
  start: string;
  end: string;
  count: number;
  series: IndicatorSeriesPoint[];
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export interface StrategyParam {
  name: string;
  type: string;
  default: number | string | null;
  min: number | null;
  max: number | null;
}

export interface StrategyInfo {
  id: string;
  label: string;
  family: string;
  description: string;
  params: StrategyParam[];
}

export interface TradeRecord {
  entry_time: string;
  exit_time: string;
  side: string;
  entry_price: number;
  exit_price: number;
  size: number;
  pnl: number;
  pnl_pct: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  drawdown: number;
}

export interface BacktestMetrics {
  total_return: number;
  sharpe: number;
  max_drawdown: number;
  n_trades: number;
  win_rate: number | null;
  avg_win: number | null;
  avg_loss: number | null;
  final_equity: number;
}

export interface BacktestResponse {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  params: Record<string, number | string>;
  initial_cash: number;
  fee: number;
  metrics: BacktestMetrics;
  equity: EquityPoint[];
  trades: TradeRecord[];
}

export interface WalkForwardWindow {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  best_params: Record<string, number | string>;
  train_sharpe: number;
  test_sharpe: number;
  test_metrics: BacktestMetrics;
}

export interface WalkForwardResponse {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  windows: WalkForwardWindow[];
  aggregate_metrics: BacktestMetrics;
}

// ---------------------------------------------------------------------------
// Regime
// ---------------------------------------------------------------------------

export interface RegimeResponse {
  symbol: string;
  timestamp: string;
  regime: string;
  confidence: number;
  adx: number;
  atr_pct: number;
  sma_slope_pct: number;
  rsi: number;
  notes: string;
}

// ---------------------------------------------------------------------------
// Replay (Phase 6 — The Living Organism)
// ---------------------------------------------------------------------------

export interface ReplayRunSummary {
  id: string;
  name: string;
  status: string;
  symbol: string;
  current_simulated_date: string | null;
  current_equity: number;
  progress_pct: number;
  n_retrains: number;
  n_kill_switch_events: number;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  created_at: string;
  final_metrics: Record<string, unknown> | null;
  config: Record<string, unknown>;
}

export interface ReplayEquityPoint {
  t: string;
  equity: number;
  position_size_pct: number;
  drawdown_pct: number;
  regime: string | null;
  n_trades_so_far: number;
}

export interface ReplayRetrainEvent {
  t: string;
  trigger: string;
  organism: Record<string, unknown>;
  elapsed_seconds: number;
  equity_at_retrain: number;
}

export interface ReplayDetailResponse {
  summary: ReplayRunSummary;
  equity_curve: ReplayEquityPoint[];
  retrain_events: ReplayRetrainEvent[];
}

export interface ReplayStartParams {
  name?: string;
  symbol?: string;
  start_date: string;
  end_date: string;
  initial_cash?: number;
  retrain_cadence_days?: number;
  lookback_days?: number;
  kill_switch_dd_pct?: number;
  kill_switch_window_days?: number;
  ga_pop_size?: number;
  ga_generations?: number;
}

export interface AdminBackfillRequest {
  symbols?: string[];
  timeframes?: string[];
  start_date: string;
  end_date?: string;
}

// ---------------------------------------------------------------------------
// System / control
// ---------------------------------------------------------------------------

export interface SystemSetting {
  key: string;
  value: Record<string, unknown>;
  description: string;
  category: string;
  schema_hint: Record<string, string>;
  updated_at: string;
}

export interface SystemSettingsList {
  settings: SystemSetting[];
}

export interface SchedulerJob {
  id: string;
  name: string;
  trigger: string;
  next_run_time: string | null;
  last_status: string | null;
  last_run_at: string | null;
  last_message: string | null;
  last_elapsed_s: number | null;
}

export interface SchedulerJobsList {
  jobs: SchedulerJob[];
}

export interface OhlcvStats {
  count: number;
  oldest: string | null;
  newest: string | null;
}

export interface MaintenanceStats {
  ohlcv: OhlcvStats;
}

export type CleanupTarget = "ohlcv_old";

export interface CleanupResult {
  target: string;
  deleted: number;
  dry_run: boolean;
  details: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// API methods
// ---------------------------------------------------------------------------

export const api = {
  // Markets / OHLCV
  markets: () => fetchJson<MarketsResponse>("/api/v1/ohlcv/markets"),

  coverage: () =>
    fetchJson<{ rows: CoverageRow[] }>("/api/v1/ohlcv/coverage").then(
      (r) => r.rows,
    ),

  ohlcv: (
    symbol: string,
    timeframe: string,
    opts: { start?: string; end?: string; limit?: number; order?: "asc" | "desc" } = {},
  ) => {
    const qs = new URLSearchParams();
    if (opts.start) qs.set("start", opts.start);
    if (opts.end) qs.set("end", opts.end);
    if (opts.limit) qs.set("limit", String(opts.limit));
    if (opts.order) qs.set("order", opts.order);
    const sym = encodeURIComponent(symbol);
    return fetchJson<OHLCVResponse>(
      `/api/v1/ohlcv/${sym}/${timeframe}?${qs.toString()}`,
    );
  },

  // Indicators
  indicators: () =>
    fetchJson<{ indicators: IndicatorInfo[] }>("/api/v1/indicators").then(
      (r) => r.indicators,
    ),

  indicatorSeries: (
    symbol: string,
    timeframe: string,
    indicator: string,
    opts: { start?: string; end?: string; limit?: number; params?: Record<string, number | string> } = {},
  ) => {
    const qs = new URLSearchParams();
    if (opts.start) qs.set("start", opts.start);
    if (opts.end) qs.set("end", opts.end);
    if (opts.limit) qs.set("limit", String(opts.limit));
    if (opts.params) {
      for (const [k, v] of Object.entries(opts.params)) {
        qs.set(`params[${k}]`, String(v));
      }
    }
    const sym = encodeURIComponent(symbol);
    return fetchJson<IndicatorResponse>(
      `/api/v1/indicators/${sym}/${timeframe}/${indicator}?${qs.toString()}`,
    );
  },

  // Backtest
  strategies: () =>
    fetchJson<{ strategies: StrategyInfo[] }>("/api/v1/backtest/strategies").then(
      (r) => r.strategies,
    ),

  runBacktest: (req: {
    symbol: string;
    timeframe: string;
    strategy_id: string;
    params?: Record<string, number | string>;
    start_date?: string;
    end_date?: string;
    initial_cash?: number;
    fee?: number;
  }) =>
    fetchJson<BacktestResponse>("/api/v1/backtest/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  runWalkForward: (req: {
    symbol: string;
    timeframe: string;
    strategy_id: string;
    n_windows: number;
    train_days: number;
    test_days: number;
    start_date?: string;
    end_date?: string;
    initial_cash?: number;
  }) =>
    fetchJson<WalkForwardResponse>("/api/v1/backtest/walk-forward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  // Regime
  regime: (symbol: string, timeframe = "1d", lookback = 120) =>
    fetchJson<RegimeResponse>(
      `/api/v1/regime/${encodeURIComponent(symbol)}?timeframe=${timeframe}&lookback_candles=${lookback}`,
    ),

  // Replay
  replayList: () =>
    fetchJson<{ runs: ReplayRunSummary[] }>("/api/v1/replay/runs"),
  replayStart: (params: ReplayStartParams) =>
    fetchJson<ReplayRunSummary>("/api/v1/replay/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),
  replayDetail: (id: string, snapshotLimit = 5000) =>
    fetchJson<ReplayDetailResponse>(
      `/api/v1/replay/runs/${id}?snapshot_limit=${snapshotLimit}`,
    ),
  replayStop: (id: string) =>
    fetchJson<{ ok: boolean; message: string }>(
      `/api/v1/replay/runs/${id}/stop`,
      { method: "POST" },
    ),
  replayDelete: (id: string) =>
    fetchJson<{ ok: boolean }>(`/api/v1/replay/runs/${id}`, { method: "DELETE" }),
  replayDeleteAll: () =>
    fetchJson<{ ok: boolean; deleted: number }>(
      "/api/v1/replay/runs?confirm=yes",
      { method: "DELETE" },
    ),
  adminBackfill: (body: AdminBackfillRequest) =>
    fetchJson<{ started: boolean; job_id: string; message: string }>(
      "/api/v1/replay/admin/backfill",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),

  // System
  systemSettings: () => fetchJson<SystemSettingsList>("/api/v1/system/settings"),

  updateSystemSetting: (key: string, value: Record<string, unknown>) =>
    fetchJson<SystemSetting>(
      `/api/v1/system/settings/${encodeURIComponent(key)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      },
    ),

  systemJobs: () => fetchJson<SchedulerJobsList>("/api/v1/system/jobs"),

  runSystemJob: (jobId: string) =>
    fetchJson<{ job_id: string; status: string }>(
      `/api/v1/system/jobs/${encodeURIComponent(jobId)}/run`,
      { method: "POST" },
    ),

  maintenanceStats: () =>
    fetchJson<MaintenanceStats>("/api/v1/system/maintenance/stats"),

  cleanup: (
    target: CleanupTarget,
    opts: { olderThanDays?: number; confirm?: boolean } = {},
  ) =>
    fetchJson<CleanupResult>("/api/v1/system/maintenance/cleanup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target,
        older_than_days: opts.olderThanDays,
        confirm: opts.confirm ?? false,
      }),
    }),
};
