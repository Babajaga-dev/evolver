import { HealthBadge } from "@/components/HealthBadge";

export default function Home() {
  return (
    <main className="min-h-screen px-4 py-12 md:px-8 md:py-20">
      <div className="mx-auto max-w-3xl">
        <p className="mb-2 text-xs uppercase tracking-[0.4em] text-[--color-gold]">
          Evolver — Phase 0
        </p>
        <h1
          className="mb-6 text-4xl md:text-6xl"
          style={{ fontFamily: "var(--font-deco)", letterSpacing: "0.1em" }}
        >
          The Genome of Markets
        </h1>
        <p className="mb-8 max-w-prose text-lg leading-relaxed text-[--color-text-secondary]">
          Sistema di trading crypto evolutivo. Algoritmi genetici, indicatori
          tecnici e regime detection convergono in una popolazione di
          strategie che evolvono per sopravvivere al mercato.
        </p>

        <div className="mt-10 border-t border-[--color-surface-border] pt-8">
          <h2
            className="mb-4 text-sm uppercase tracking-[0.3em] text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            System Status
          </h2>
          <HealthBadge />
        </div>

        <nav
          className="mt-12 flex flex-wrap gap-x-6 gap-y-2 border-t border-[--color-surface-border] pt-6 text-sm uppercase tracking-[0.25em] text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          <a className="hover:text-[--color-gold]" href="/data">
            ◆ Data Explorer
          </a>
          <a className="hover:text-[--color-gold]" href="/backtest">
            ◆ Backtest
          </a>
          <a className="hover:text-[--color-gold]" href="/population">
            ◆ Population
          </a>
          <a className="hover:text-[--color-gold]" href="/paper">
            ◆ Paper
          </a>
          <a className="hover:text-[--color-gold]" href="/regime">
            ◆ Regime
          </a>
          <a className="hover:text-[--color-gold]" href="/replay">
            ◆ Replay
          </a>
          <a className="hover:text-[--color-gold]" href="/oos">
            ◆ OOS
          </a>
          <a className="hover:text-[--color-gold]" href="/control">
            ◆ Control
          </a>
        </nav>

        <footer className="mt-20 text-xs text-[--color-text-muted]">
          <p>
            Paper trading mode · v0.1.0 · Costruito per BTC + ETH su Binance
          </p>
        </footer>
      </div>
    </main>
  );
}
