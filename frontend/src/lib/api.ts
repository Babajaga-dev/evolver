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
// Backtest
// ---------------------------------------------------------------------------

export interface StrategyParamInfo {
  name: string;
  type: "int" | "float" | "str";
  default: number | string;
  min?: number | null;
  max?: number | null;
  description?: string;
}

export interface StrategyInfo {
  id: string;
  label: string;
  family: "trend_follow" | "mean_reversion" | "breakout" | "volatility";
  description: string;
  params: StrategyParamInfo[];
}

export interface StrategiesRegistryResponse {
  strategies: StrategyInfo[];
}

export interface BacktestRequest {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  params: Record<string, number | string>;
  period_days: number;
  initial_cash: number;
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

// ---------------------------------------------------------------------------
// Walk-forward
// ---------------------------------------------------------------------------

export interface WalkForwardRequest {
  symbol: string;
  timeframe: string;
  strategy_id: string;
  params: Record<string, number | string>;
  period_days: number;
  initial_cash: number;
  n_windows: number;
}

export interface WindowResult {
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

export type WalkForwardVerdict =
  | "robust"
  | "mixed"
  | "unstable"
  | "no_signal";

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
  verdict: WalkForwardVerdict;
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
  windows: WindowResult[];
  summary: WalkForwardSummary;
}

// ---------------------------------------------------------------------------
// GA — genetic algorithm runs
// ---------------------------------------------------------------------------

export interface GaRunRequest {
  strategy_id: string;
  symbol: string;
  timeframe: string;
  period_days: number;
  initial_cash: number;
  population_size: number;
  n_generations: number;
  n_windows: number;
  seed: number;
}

export interface GaRunCreated {
  population_id: string;
  status: string;
  message: string;
}

export interface GenerationSnapshotOut {
  generation: number;
  best_fitness: number;
  mean_fitness: number;
  worst_fitness: number;
  std_fitness: number;
  best_sharpe_robust: number;
  best_max_dd: number;
  diversity: number;
  elapsed_seconds: number;
}

export interface StrategySnapshotOut {
  chromosome: Record<string, number | string>;
  sharpe_robust: number;
  max_drawdown_abs: number;
  complexity: number;
  n_trades: number;
  n_windows_winning: number;
  generation: number;
}

export type GaRunStatusValue =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export interface GaRunStatus {
  population_id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  status: GaRunStatusValue;
  current_generation: number;
  total_generations: number;
  population_size: number;
  started_at: string | null;
  completed_at: string | null;
  elapsed_seconds: number;
  error: string | null;
  generations: GenerationSnapshotOut[];
  pareto_front: StrategySnapshotOut[];
  top_strategies: StrategySnapshotOut[];
}

export interface GaRunSummary {
  population_id: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  status: GaRunStatusValue;
  current_generation: number;
  total_generations: number;
  started_at: string | null;
  best_sharpe_robust: number | null;
}

export interface GaRunsListResponse {
  runs: GaRunSummary[];
}

// ---------------------------------------------------------------------------
// News
// ---------------------------------------------------------------------------

export interface NewsScore {
  assets_mentioned: string[];
  event_type: string;
  factual_impact: number;
  sentiment_score: number;
  confidence: number;
  ttl_hours: number;
  reasoning: string | null;
  model: string;
  scored_at: string;
}

export interface NewsItem {
  id: string;
  source: string;
  url: string;
  title: string;
  body: string | null;
  published_at: string;
  ingested_at: string;
  score: NewsScore | null;
}

export interface NewsListResponse {
  items: NewsItem[];
  count: number;
}

export interface NewsStats {
  total_raw: number;
  total_scored: number;
  scored_last_24h: number;
  avg_sentiment_24h: number;
  by_event_type_24h: Record<string, number>;
}

export interface AssetSentiment {
  asset: string;
  hours: number;
  n_news: number;
  avg_sentiment: number;
  avg_factual_impact: number;
  avg_confidence: number;
  weighted_signal: number;
  by_event_type: Record<string, number>;
  freshest_at: string | null;
}

// ---------------------------------------------------------------------------
// Paper trading
// ---------------------------------------------------------------------------

export interface PaperStateResponse {
  portfolio_id: string;
  initial_balance: number;
  balance_quote: number;
  holdings: Record<string, unknown>;
  equity: number;
  drawdown_from_peak: number;
  open_positions_count: number;
  last_snapshot_at: string | null;
  total_return_pct: number;
  trades_total: number;
  trades_open: number;
  trades_closed: number;
  trades_winning: number;
  win_rate: number;
  total_pnl: number;
  status: string;
}

export interface PaperTradeOut {
  id: string;
  strategy_id: string | null;
  symbol: string;
  timeframe: string;
  side: string;
  status: string;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  entry_time: string;
  exit_time: string | null;
  fees: number;
  pnl: number | null;
  pnl_pct: number | null;
}

export interface PaperTradesResponse {
  trades: PaperTradeOut[];
  count: number;
}

export interface PaperEquityPoint {
  timestamp: string;
  equity: number;
  balance_quote: number;
  drawdown_from_peak: number;
  open_positions_count: number;
}

export interface EquityCurveResponse {
  portfolio_id: string;
  points: PaperEquityPoint[];
  count: number;
}

// ---------------------------------------------------------------------------
// Postmortem (Claude Opus weekly review)
// ---------------------------------------------------------------------------

export interface PostmortemResponse {
  period_start: string;
  period_end: string;
  markdown: string;
  model: string;
  tokens_input: number;
  tokens_output: number;
  cost_usd_estimate: number;
}

// ---------------------------------------------------------------------------
// Regime detector
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

export interface NewsRefreshResponse {
  fetched: number;
  inserted: number;
}

export interface NewsScoreBatchResponse {
  picked: number;
  scored: number;
  failed: number;
}

// ---------------------------------------------------------------------------
// System (control panel)
// ---------------------------------------------------------------------------

export interface SystemSetting {
  key: string;
  value: Record<string, unknown>;
  description: string | null;
  category: string;
  schema_hint: Record<string, string>;
  updated_at: string | null;
}

export interface SystemSettingsList {
  settings: SystemSetting[];
}

export interface SchedulerJob {
  id: string;
  name: string;
  next_run: string | null;
  trigger: string;
  last_run_at: string | null;
  last_status: string | null;
  last_message: string | null;
  last_duration_s: number | null;
}

export interface SchedulerJobsList {
  jobs: SchedulerJob[];
}

export interface MaintenanceStats {
  ohlcv: {
    count: number;
    oldest: string | null;
    newest: string | null;
  };
  news: {
    raw: number;
    scored: number;
    pending: number;
  };
  ga_postgres: {
    populations: number;
    generations: number;
    strategies: number;
    fitness_evaluations: number;
  };
  ga_redis: {
    total: number;
    by_status: Record<string, number>;
  };
}

export type CleanupTarget =
  | "ohlcv_old"
  | "news_raw_old"
  | "news_scored_all"
  | "ga_runs_failed"
  | "ga_runs_completed"
  | "ga_runs_all";

export interface CleanupResult {
  target: string;
  deleted: number;
  dry_run: boolean;
  details: Record<string, unknown>;
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

  strategiesRegistry: () =>
    fetchJson<StrategiesRegistryResponse>("/api/v1/strategies"),

  runBacktest: (req: BacktestRequest) =>
    fetchJson<BacktestResponse>("/api/v1/backtest/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  runWalkForward: (req: WalkForwardRequest) =>
    fetchJson<WalkForwardResponse>("/api/v1/backtest/walk-forward", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  startGaRun: (req: GaRunRequest) =>
    fetchJson<GaRunCreated>("/api/v1/ga/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  getGaRun: (populationId: string) =>
    fetchJson<GaRunStatus>(`/api/v1/ga/runs/${populationId}`),

  listGaRuns: () => fetchJson<GaRunsListResponse>("/api/v1/ga/runs"),

  stopGaRun: (populationId: string) =>
    fetchJson<{ population_id: string; status: string; message: string }>(
      `/api/v1/ga/runs/${populationId}/stop`,
      { method: "POST" },
    ),

  deleteGaRun: (populationId: string) =>
    fetchJson<{ population_id: string; deleted: boolean }>(
      `/api/v1/ga/runs/${populationId}`,
      { method: "DELETE" },
    ),

  cleanupGaRuns: (statusFilter?: string) => {
    const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
    return fetchJson<{ deleted: number; ids: string[] }>(
      `/api/v1/ga/runs${qs}`,
      { method: "DELETE" },
    );
  },

  // ---- News ----

  listNews: (
    opts: {
      limit?: number;
      asset?: string;
      eventType?: string;
      onlyScored?: boolean;
    } = {},
  ) => {
    const params = new URLSearchParams();
    if (opts.limit) params.set("limit", String(opts.limit));
    if (opts.asset) params.set("asset", opts.asset);
    if (opts.eventType) params.set("event_type", opts.eventType);
    if (opts.onlyScored !== undefined)
      params.set("only_scored", String(opts.onlyScored));
    const qs = params.toString();
    return fetchJson<NewsListResponse>(`/api/v1/news${qs ? `?${qs}` : ""}`);
  },

  newsStats: () => fetchJson<NewsStats>("/api/v1/news/stats"),

  assetSentiment: (asset: string, hours = 24) =>
    fetchJson<AssetSentiment>(
      `/api/v1/news/sentiment/${encodeURIComponent(asset)}?hours=${hours}`,
    ),

  // ---- Paper trading ----

  paperState: (portfolioId = "paper-v1") =>
    fetchJson<PaperStateResponse>(
      `/api/v1/paper/state?portfolio_id=${encodeURIComponent(portfolioId)}`,
    ),

  paperTrades: (limit = 100, status?: string) => {
    const qs = new URLSearchParams();
    qs.set("limit", String(limit));
    if (status) qs.set("status", status);
    return fetchJson<PaperTradesResponse>(`/api/v1/paper/trades?${qs.toString()}`);
  },

  paperEquity: (hours = 168, maxPoints = 500, portfolioId = "paper-v1") =>
    fetchJson<EquityCurveResponse>(
      `/api/v1/paper/equity?portfolio_id=${encodeURIComponent(portfolioId)}&hours=${hours}&max_points=${maxPoints}`,
    ),

  paperCreateSnapshot: (portfolioId = "paper-v1") =>
    fetchJson<{ portfolio_id: string; snapshot_at: string; equity: number; message: string }>(
      `/api/v1/paper/snapshot?portfolio_id=${encodeURIComponent(portfolioId)}`,
      { method: "POST" },
    ),

  // ---- Postmortem ----

  postmortemGenerate: (days = 7) =>
    fetchJson<PostmortemResponse>("/api/v1/postmortem/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ days }),
    }),

  // ---- Regime detector ----

  regime: (symbol: string, timeframe = "1d", lookback = 120) =>
    fetchJson<RegimeResponse>(
      `/api/v1/regime/${encodeURIComponent(symbol)}?timeframe=${timeframe}&lookback_candles=${lookback}`,
    ),

  refreshNews: () =>
    fetchJson<NewsRefreshResponse>("/api/v1/news/refresh", { method: "POST" }),

  scoreNewsBatch: (limit = 20, concurrency = 4) =>
    fetchJson<NewsScoreBatchResponse>(
      `/api/v1/news/score?limit=${limit}&concurrency=${concurrency}`,
      { method: "POST" },
    ),

  // ---- System / control panel ----

  systemSettings: () =>
    fetchJson<SystemSettingsList>("/api/v1/system/settings"),

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
};

export { ApiError };
