"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { StrategySnapshotOut } from "@/lib/api";

interface Props {
  /** Cromosomi della generazione corrente (o ultima disponibile). */
  strategies: StrategySnapshotOut[];
  /** Numero di bin per histogram (default 10). */
  nBins?: number;
}

interface ParamHistogram {
  paramName: string;
  isInteger: boolean;
  bins: { label: string; count: number; mid: number }[];
  min: number;
  max: number;
  mean: number;
}

/**
 * Per ogni parametro numerico del cromosoma, mostra un mini bar chart con
 * la distribuzione dei valori nella popolazione corrente. Convergenza
 * visibile come istogramma che si concentra in un range stretto.
 */
export function ParameterHistograms({ strategies, nBins = 10 }: Props) {
  const histograms = useMemo<ParamHistogram[]>(() => {
    if (strategies.length === 0) return [];

    // Estrai tutti i nomi di params numerici dal primo cromosoma
    const first = strategies[0].chromosome;
    const paramNames = Object.entries(first)
      .filter(([_, v]) => typeof v === "number")
      .map(([k]) => k);

    return paramNames.map((name) => {
      const values: number[] = strategies
        .map((s) => s.chromosome[name])
        .filter((v): v is number => typeof v === "number");

      const min = Math.min(...values);
      const max = Math.max(...values);
      const mean = values.reduce((a, b) => a + b, 0) / values.length;
      const isInteger = values.every((v) => Number.isInteger(v));

      // Bins
      let actualBins = nBins;
      let binWidth = (max - min) / nBins;
      if (isInteger) {
        // Per int, usa bin width almeno 1
        actualBins = Math.min(nBins, Math.max(1, Math.ceil(max - min + 1)));
        binWidth = (max - min) / actualBins || 1;
      }
      if (binWidth === 0 || !Number.isFinite(binWidth)) {
        // Tutti uguali
        return {
          paramName: name,
          isInteger,
          bins: [
            {
              label: isInteger ? String(Math.round(mean)) : mean.toFixed(2),
              count: values.length,
              mid: mean,
            },
          ],
          min,
          max,
          mean,
        };
      }

      const bins: { label: string; count: number; mid: number }[] = [];
      for (let i = 0; i < actualBins; i++) {
        const lo = min + i * binWidth;
        const hi = i === actualBins - 1 ? max : lo + binWidth;
        const mid = (lo + hi) / 2;
        const count = values.filter((v) => v >= lo && (i === actualBins - 1 ? v <= hi : v < hi)).length;
        bins.push({
          label: isInteger
            ? `${Math.round(lo)}-${Math.round(hi)}`
            : `${lo.toFixed(1)}-${hi.toFixed(1)}`,
          count,
          mid,
        });
      }

      return {
        paramName: name,
        isInteger,
        bins,
        min,
        max,
        mean,
      };
    });
  }, [strategies, nBins]);

  if (histograms.length === 0) {
    return (
      <p className="font-mono text-xs text-[--color-text-muted]">
        Aspettando dati popolazione…
      </p>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {histograms.map((h) => (
        <SingleHistogram key={h.paramName} h={h} />
      ))}
    </div>
  );
}

function SingleHistogram({ h }: { h: ParamHistogram }) {
  return (
    <div className="border border-[--color-surface-border] bg-[--color-surface] p-3">
      <div className="mb-1 flex items-baseline justify-between">
        <span
          className="font-mono text-[10px] uppercase tracking-[0.25em] text-[--color-gold]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          {h.paramName}
        </span>
        <span className="font-mono text-[10px] text-[--color-text-muted]">
          μ={h.isInteger ? Math.round(h.mean) : h.mean.toFixed(2)} · range [
          {h.isInteger ? Math.round(h.min) : h.min.toFixed(2)},{" "}
          {h.isInteger ? Math.round(h.max) : h.max.toFixed(2)}]
        </span>
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={h.bins} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--color-surface-border)" />
          <XAxis
            dataKey="label"
            tick={{
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 8,
            }}
            stroke="var(--color-surface-border)"
            interval={0}
            angle={h.bins.length > 5 ? -45 : 0}
            textAnchor={h.bins.length > 5 ? "end" : "middle"}
            height={h.bins.length > 5 ? 30 : 16}
          />
          <YAxis
            tick={{
              fill: "var(--color-text-muted)",
              fontFamily: "var(--font-mono)",
              fontSize: 8,
            }}
            allowDecimals={false}
            width={20}
            stroke="var(--color-surface-border)"
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-surface-card)",
              border: "1px solid var(--color-gold)",
              borderRadius: 0,
              fontFamily: "var(--font-mono)",
              fontSize: 10,
            }}
            labelStyle={{ color: "var(--color-gold)" }}
            itemStyle={{ color: "var(--color-text-primary)" }}
            cursor={{ fill: "var(--color-surface-elevated)", opacity: 0.4 }}
          />
          <Bar
            dataKey="count"
            fill="var(--color-btc)"
            isAnimationActive
            animationDuration={400}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
