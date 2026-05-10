"use client";

import { RegimeBadge } from "@/components/RegimeBadge";

export default function RegimePage() {
  return (
    <main className="min-h-screen px-4 py-8 md:px-8 md:py-12">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p
              className="mb-1 text-xs uppercase tracking-[0.4em] text-[--color-gold]"
              style={{ fontFamily: "var(--font-serif)" }}
            >
              Phase 5 · Multi-Timeframe Orchestration
            </p>
            <h1
              className="text-3xl md:text-5xl"
              style={{
                fontFamily: "var(--font-deco)",
                letterSpacing: "0.08em",
              }}
            >
              The Tide Watcher
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-[--color-text-secondary]">
              Detector di regime macro su candele 1d. Distinguere
              trend (ADX&gt;25) da range (ADX&lt;20), con bias direzionale
              dalla SMA(50) slope. I valori guidano GA fitness, paper
              engine sizing, postmortem cross-validation.
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

        <section className="mb-8 grid gap-4 md:grid-cols-2">
          <RegimeBadge symbol="BTC/USDT" />
          <RegimeBadge symbol="ETH/USDT" />
        </section>

        <section
          className="border border-[--color-surface-border] bg-[--color-surface-card] p-6 text-sm leading-relaxed text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-body, var(--font-serif))" }}
        >
          <h2
            className="mb-3 text-xs uppercase tracking-[0.3em] text-[--color-gold]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            Reading the Tide
          </h2>
          <p>
            <strong>Trend bullish/bearish</strong> (ADX&gt;25 + SMA slope ±):
            il mercato si muove con direzione. Strategie trend-follow (EMA cross,
            Bollinger breakout) prevalgono. Mean-reversion sconsigliata.
          </p>
          <p className="mt-3">
            <strong>Range low_vol</strong> (ADX&lt;20 + ATR&lt;1.5%): mercato
            tranquillo, oscillazioni piccole. RSI mean-reversion ottimale,
            obiettivi profit modesti, stop loss stretti.
          </p>
          <p className="mt-3">
            <strong>Range high_vol</strong> (ADX&lt;20 + ATR&gt;4%): consolidamento
            volatile (es. dopo eventi macro). Mean-reversion possibile ma con
            stop loss più larghi e size ridotta.
          </p>
          <p className="mt-3">
            <strong>Transition</strong> (ADX 20-25): zona grigia. Aspettare
            conferma prima di posizionarsi.
          </p>
        </section>

        <footer
          className="mt-12 border-t border-[--color-surface-border] pt-4 text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          Auto-refresh ogni 5 min · ADX/ATR/SMA/RSI da pandas-ta-classic
        </footer>
      </div>
    </main>
  );
}
