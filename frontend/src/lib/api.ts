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
  symbol: string;
  timeframe: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

export interface OHLCVResponse {
  symbol: string;
  timeframe: string;
  count: number;
  candles: Candle[];
}

export interface MarketsResponse {
  symbols: string[];
  timeframes: string[];
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
  exit_time: string | null;
  entry_price: number;
  exit_price: number | null;
  size: number;
  direction: string;
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
  sharpe: number | null;
  sortino: number | null;
  calmar: number | null;
  max_drawdown: number;
  win_rate: number | null;
  profit_factor: number | null;
  n_trades: number;
  avg_trade_pct: number | null;
  final_equity: number;
}

export interface BacktestResponse {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  strategy_label: string;
  params: Record<string, number | string>;
  initial_cash: number;
  fee: number;
  slippage: number;
  start: string;
  end: string;
  equity_curve: EquityPoint[];
  trades: TradeRecord[];
  metrics: BacktestMetrics;
}

export type WalkForwardVerdict = "robust" | "mixed" | "unstable" | "no_signal";

export interface WalkForwardWindow {
  window_index: number;
  window_start: string;
  window_end: string;
  n_candles: number;
  n_trades: number;
  total_return: number;
  sharpe: number | null;
  calmar: number | null;
  max_drawdown: number;
  win_rate: number | null;
  final_equity: number;
}

export type WindowResult = WalkForwardWindow;

export interface WalkForwardSummary {
  n_windows: number;
  n_windows_winning: number;
  n_windows_with_trades: number;
  mean_total_return: number;
  std_total_return: number;
  mean_sharpe: number | null;
  std_sharpe: number | null;
  mean_max_drawdown: number;
  worst_max_drawdown: number;
  best_total_return: number;
  worst_total_return: number;
  verdict: string;
  verdict_reason: string;
}

export interface WalkForwardResponse {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  strategy_label: string;
  params: Record<string, number | string>;
  initial_cash: number;
  n_windows: number;
  period_start: string;
  period_end: string;
  windows: WalkForwardWindow[];
  summary: WalkForwardSummary;
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

// Risk Allocator (combines TREND + STAT-ARB + CARRY + F&G overlay)
export interface AllocatorRunRequest {
  symbols?: string[];
  timeframe?: string;
  start_date: string;
  end_date: string;
  initial_cash?: number;
  rolling_sharpe_days?: number;
  rebalance_days?: number;
  apply_fng_overlay?: boolean;
  apply_gate_overlay?: boolean;
  run_trend?: boolean;
  run_statarb?: boolean;
  run_carry?: boolean;
  statarb_symbol_a?: string;
  statarb_symbol_b?: string;
}

export interface AllocatorPoint {
  t: string;
  equity: number;
  weight_trend: number;
  weight_statarb: number;
  weight_carry: number;
  fng_ema: number | null;
  regime: string;
  gate_active: boolean;
}

export interface AllocatorResponse {
  start_date: string;
  end_date: string;
  initial_cash: number;
  final_equity: number;
  total_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  correlation_matrix: Record<string, Record<string, number>>;
  per_engine_contribution: Record<string, number>;
  per_engine_metrics: Record<string, {
    sharpe: number;
    return: number;
    max_drawdown: number;
    n_trades: number;
    beta_vs_btc?: number;
  }>;
  equity_curve: AllocatorPoint[];
  config: {
    rolling_sharpe_days: number;
    rebalance_days: number;
    fng_overlay_applied: boolean;
    engines_active: string[];
  };
}

// STAT-ARB pairs trade (paper IJSRA 2026-0283 BTC-ETH cointegration)
export interface StatArbRunRequest {
  symbol_a?: string;
  symbol_b?: string;
  timeframe?: string;
  start_date: string;
  end_date: string;
  initial_cash?: number;
  lookback_bars?: number;
  z_entry?: number;
  z_exit?: number;
  z_stop?: number;
  max_half_life_bars?: number;
  capital_per_trade?: number;
  fee_bps?: number;
  slippage_bps?: number;
}

export interface StatArbEquityPoint {
  t: string;
  equity: number;
  spread: number;
  zscore: number;
  hedge_ratio: number;
  position: number;
}

export interface StatArbTradeOut {
  entry_time: string;
  exit_time: string;
  side: "long_spread" | "short_spread";
  entry_spread: number;
  exit_spread: number;
  entry_z: number;
  exit_z: number;
  qty_a: number;
  qty_b: number;
  pnl: number;
  pnl_pct: number;
  holding_bars: number;
  reason: string;
}

export interface StatArbMonthlyReturn {
  month: string;
  return_pct: number;
  n_trades: number;
}

export interface StatArbResponse {
  symbol_a: string;
  symbol_b: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  n_trades: number;
  n_winners: number;
  initial_cash: number;
  final_equity: number;
  total_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  win_rate: number;
  avg_holding_bars: number;
  beta_vs_btc: number;
  avg_hedge_ratio: number;
  cointegration_p_value: number;
  equity_curve: StatArbEquityPoint[];
  trades: StatArbTradeOut[];
  monthly_returns: StatArbMonthlyReturn[];
}

// TREND Donchian ensemble (paper AdaptiveTrend arXiv 2602.11708)
export interface TrendRunRequest {
  symbols?: string[];
  timeframe?: string;
  start_date: string;
  end_date: string;
  initial_cash?: number;
  lookbacks?: number[];
  target_vol_annual?: number;
  trailing_stop_atr_mult?: number;
  rebalance_days?: number;
  top_n_assets?: number;
  long_weight?: number;
  short_weight?: number;
  fee_bps?: number;
  slippage_bps?: number;
}

export interface TrendEquityPoint {
  t: string;
  equity: number;
  exposure_pct: number;
  n_positions: number;
}

export interface TrendTradeOut {
  symbol: string;
  side: "long" | "short";
  entry_time: string;
  entry_price: number;
  exit_time: string;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  holding_days: number;
  reason: string;
}

export interface TrendMonthlyReturn {
  month: string;
  return_pct: number;
  n_trades: number;
}

export interface TrendAssetStat {
  symbol: string;
  n_trades: number;
  n_winners: number;
  total_pnl: number;
  avg_pnl_pct: number;
}

export interface TrendResponse {
  symbols: string[];
  timeframe: string;
  start_date: string;
  end_date: string;
  n_trades: number;
  n_long_trades: number;
  n_short_trades: number;
  initial_cash: number;
  final_equity: number;
  total_return: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  win_rate: number;
  avg_pnl_pct: number;
  monthly_returns: TrendMonthlyReturn[];
  equity_curve: TrendEquityPoint[];
  trades: TrendTradeOut[];
  per_asset_stats: TrendAssetStat[];
  baselines: {
    buy_hold_equal_weight: {
      sharpe: number;
      total_return: number;
      max_drawdown: number;
      final_equity: number;
    };
    per_asset_buy_hold: Array<{
      symbol: string;
      sharpe: number;
      total_return: number;
      max_drawdown: number;
      final_equity: number;
    }>;
  };
}

// Sentiment Fear & Greed (paper Zhang-Watts arXiv 2512.02029)
export interface FngPoint {
  date: string;
  value: number;
  classification: string;
  ema_24w: number | null;
  zone: "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed";
}

export interface FngSeriesResponse {
  start_date: string;
  end_date: string;
  n_points: number;
  points: FngPoint[];
  summary: {
    current_value: number;
    current_ema_24w: number;
    current_zone: string;
    min_value: number;
    max_value: number;
    mean_value: number;
    mean_ema_24w: number;
    n_extreme_fear_days: number;
    n_extreme_greed_days: number;
  };
}

export interface FngStats {
  total_entries: number;
  latest_date: string | null;
  latest_value: number | null;
  latest_classification: string | null;
}

export interface FngBackfillResponse {
  started: boolean;
  job_id: string;
  message: string;
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
    fetchJson<CoverageRow[]>("/api/v1/ohlcv/coverage"),

  ohlcv: (
    symbol: string,
    timeframe: string,
    opts: { start?: string | Date; end?: string | Date; limit?: number; order?: "asc" | "desc" } = {},
  ) => {
    const qs = new URLSearchParams();
    const toIso = (v: string | Date | undefined) =>
      v === undefined ? undefined : (v instanceof Date ? v.toISOString() : v);
    const s = toIso(opts.start);
    const e = toIso(opts.end);
    if (s) qs.set("start", s);
    if (e) qs.set("end", e);
    if (opts.limit) qs.set("limit", String(opts.limit));
    if (opts.order) qs.set("order", opts.order);
    const sym = encodeURIComponent(symbol);
    return fetchJson<OHLCVResponse>(
      `/api/v1/ohlcv/${sym}/${timeframe}?${qs.toString()}`,
    );
  },

  // Indicators
  indicators: () =>
    fetchJson<{ indicators: IndicatorInfo[] }>("/api/v1/indicators"),

  indicator: (
    symbol: string,
    timeframe: string,
    indicator: string,
    params: Record<string, number | string> | null | undefined,
    opts: { start?: string | Date; end?: string | Date; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    const toIso = (v: string | Date | undefined) =>
      v === undefined ? undefined : (v instanceof Date ? v.toISOString() : v);
    const s = toIso(opts.start);
    const e = toIso(opts.end);
    if (s) qs.set("start", s);
    if (e) qs.set("end", e);
    if (opts.limit) qs.set("limit", String(opts.limit));
    if (params) {
      for (const [k, v] of Object.entries(params)) {
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
    fetchJson<{ strategies: StrategyInfo[] }>("/api/v1/backtest/strategies"),

  runBacktest: (req: {
    symbol: string;
    timeframe: string;
    strategy_id: string;
    params?: Record<string, number | string>;
    period_days?: number;
    initial_cash?: number;
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
    params?: Record<string, number | string>;
    period_days?: number;
    initial_cash?: number;
    n_windows?: number;
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
    fetchJson<{ id: string; triggered: boolean; message: string }>(
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




  allocatorRun: (body: AllocatorRunRequest) =>
    fetchJson<AllocatorResponse>("/api/v1/allocator/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  statarbRun: (body: StatArbRunRequest) =>
    fetchJson<StatArbResponse>("/api/v1/statarb/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  trendRun: (body: TrendRunRequest) =>
    fetchJson<TrendResponse>("/api/v1/trend/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // Sentiment Fear & Greed
  fngSeries: (opts: { start?: string | Date; end?: string | Date; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    const toIso = (v: string | Date | undefined) =>
      v === undefined ? undefined : (v instanceof Date ? v.toISOString() : v);
    const s = toIso(opts.start);
    const e = toIso(opts.end);
    if (s) qs.set("start_date", s);
    if (e) qs.set("end_date", e);
    if (opts.limit) qs.set("limit", String(opts.limit));
    return fetchJson<FngSeriesResponse>(`/api/v1/sentiment/fng?${qs.toString()}`);
  },

  fngStats: () => fetchJson<FngStats>("/api/v1/sentiment/stats"),

  fngBackfill: (limit: number = 0) =>
    fetchJson<FngBackfillResponse>("/api/v1/sentiment/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit }),
    }),
};
