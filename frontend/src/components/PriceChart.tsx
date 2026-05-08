"use client";

import { useMemo } from "react";
import {
  Area,
  ComposedChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { IndicatorResponse, OHLCVCandle } from "@/lib/api";

/** Una sovrapposizione (line) sul chart prezzo. Indicatori "overlay" come
 *  EMA, SMA, BBands. Le linee sono identificate da ``key`` e disegnate con
 *  ``color``. */
export interface PriceOverlay {
  /** Identificatore univoco per la dataKey nel chart (es. "ema_50"). */
  key: string;
  /** Etichetta human-readable per legenda/tooltip (es. "EMA(50)"). */
  label: string;
  /** Colore CSS della linea. */
  color: string;
  /** Punti allineati per timestamp ISO (sparso accettato). */
  series: { timestamp: string; value: number | null }[];
  /** Stile linea opzionale (es. tratteggio per medie lente). */
  strokeDasharray?: string;
}

interface Props {
  candles: OHLCVCandle[];
  overlays?: PriceOverlay[];
  height?: number;
}

interface ChartPoint {
  ts: number;
  label: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  // Le overlay vengono iniettate dinamicamente con chiavi `overlays[i].key`.
  [overlayKey: string]: number | string | null;
}

export function PriceChart({ candles, overlays = [], height = 360 }: Props) {
  const data = useMemo<ChartPoint[]>(() => {
    // Indicizza ogni overlay per timestamp per join veloce
    const overlayMaps = overlays.map((o) => {
      const m = new Map<string, number | null>();
      for (const p of o.series) m.set(p.timestamp, p.value);
      return { key: o.key, map: m };
    });

    return candles.map((c) => {
      const date = new Date(c.timestamp);
      const point: ChartPoint = {
        ts: date.getTime(),
        label: formatTs(date),
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
        volume: Number(c.volume),
      };
      for (const { key, map } of overlayMaps) {
        const v = map.get(c.timestamp);
        point[key] = v ?? null;
      }
      return point;
    });
  }, [candles, overlays]);

  if (data.length === 0) {
    return (
      <div
        className="flex items-center justify-center font-mono text-sm text-[--color-text-muted]"
        style={{ height }}
      >
        No data — try a different range or wait for backfill to complete.
      </div>
    );
  }

  // Y-domain calcolato includendo overlays (per non tagliare BBands o EMA)
  const allValues: number[] = [];
  for (const p of data) {
    allValues.push(p.close);
    for (const o of overlays) {
      const v = p[o.key];
      if (typeof v === "number" && Number.isFinite(v)) allValues.push(v);
    }
  }
  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const yPadding = (maxV - minV) * 0.05 || 1;
  const yDomain: [number, number] = [minV - yPadding, maxV + yPadding];

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
        >
          <defs>
            <linearGradient id="closeFill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="var(--color-btc)"
                stopOpacity={0.45}
              />
              <stop
                offset="100%"
                stopColor="var(--color-btc)"
                stopOpacity={0.0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid
            strokeDasharray="2 4"
            stroke="var(--color-surface-border)"
          />
          <XAxis
            dataKey="label"
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickMargin={6}
            interval="preserveStartEnd"
            minTickGap={48}
            stroke="var(--color-surface-border)"
          />
          <YAxis
            domain={yDomain}
            tick={{
              fill: "var(--color-text-secondary)",
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            tickFormatter={(v) => v.toFixed(0)}
            width={64}
            stroke="var(--color-surface-border)"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              borderRadius: 0,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--color-gold)" }}
            itemStyle={{ color: "var(--color-text-primary)" }}
            formatter={(value: number, name) => [
              typeof value === "number" ? value.toFixed(2) : "—",
              name,
            ]}
          />
          <Area
            type="monotone"
            dataKey="close"
            name="Close"
            stroke="var(--color-btc)"
            strokeWidth={1.5}
            fill="url(#closeFill)"
            isAnimationActive={false}
          />
          {overlays.map((o) => (
            <Line
              key={o.key}
              type="monotone"
              dataKey={o.key}
              name={o.label}
              stroke={o.color}
              strokeWidth={1.2}
              strokeDasharray={o.strokeDasharray}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function formatTs(d: Date): string {
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mi = String(d.getUTCMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * Helper: trasforma una IndicatorResponse di tipo "overlay" in array di
 * PriceOverlay (uno per output_key).
 */
export function indicatorToOverlays(
  ind: IndicatorResponse,
  colors: string[] = OVERLAY_COLORS,
): PriceOverlay[] {
  return ind.output_keys.map((key, i) => ({
    key: `${ind.indicator}_${key}_${seedFromParams(ind.params)}`,
    label: `${ind.label} ${formatParams(ind.params)} · ${key}`,
    color: colors[i % colors.length],
    series: ind.points.map((p) => ({
      timestamp: p.timestamp,
      value: p.values[key] ?? null,
    })),
    // BBands lower/upper tratteggio leggero per distinguerli dal middle
    strokeDasharray:
      ind.indicator === "bbands" && key !== "middle" ? "3 3" : undefined,
  }));
}

const OVERLAY_COLORS = [
  "#7799ff", // blue (epic tier)
  "#bb77ff", // purple (rare tier)
  "#00ff99", // green (common tier)
  "#f4a261", // gold electric
];

function formatParams(params: Record<string, number | string>): string {
  const flat = Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join(",");
  return flat ? `(${flat})` : "";
}

function seedFromParams(params: Record<string, number | string>): string {
  return Object.values(params).join("_");
}
