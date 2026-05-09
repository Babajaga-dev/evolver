"use client";

interface Props {
  /** Modalità: ``indeterminate`` (loading senza progress noto), ``determinate``
   *  (value 0-1). */
  mode?: "indeterminate" | "determinate";
  /** Per la modalità determinate: progress 0..1. Ignorato in indeterminate. */
  value?: number;
  /** Etichetta a sinistra (es. "Backtest in corso"). */
  label?: string;
  /** Etichetta a destra (es. "3/5 finestre · 12s"). */
  detail?: string;
  /** Altezza pixel della barra. */
  height?: number;
}

export function ProgressBar({
  mode = "indeterminate",
  value = 0,
  label,
  detail,
  height = 6,
}: Props) {
  const clamped = Math.max(0, Math.min(1, value));
  const pct = `${(clamped * 100).toFixed(1)}%`;

  return (
    <div className="w-full">
      {(label || detail) && (
        <div
          className="mb-1.5 flex items-baseline justify-between font-mono text-[11px] uppercase tracking-[0.25em]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          <span className="text-[--color-gold]">{label ?? " "}</span>
          <span className="text-[--color-text-secondary]">
            {detail ?? " "}
          </span>
        </div>
      )}
      <div
        className="relative w-full overflow-hidden border border-[--color-surface-border] bg-[--color-surface]"
        style={{ height }}
      >
        {mode === "determinate" ? (
          <div
            className="h-full transition-all duration-300 ease-out"
            style={{
              width: pct,
              background:
                "linear-gradient(90deg, var(--color-gold), var(--color-btc))",
            }}
          />
        ) : (
          <div className="evolver-indeterminate h-full" />
        )}
      </div>
      <style jsx>{`
        @keyframes evolverIndeterminate {
          0% {
            transform: translateX(-100%);
          }
          50% {
            transform: translateX(0%);
          }
          100% {
            transform: translateX(100%);
          }
        }
        .evolver-indeterminate {
          width: 40%;
          background: linear-gradient(
            90deg,
            transparent,
            var(--color-gold),
            var(--color-btc),
            var(--color-gold),
            transparent
          );
          animation: evolverIndeterminate 1.4s ease-in-out infinite;
          will-change: transform;
        }
        @media (prefers-reduced-motion: reduce) {
          .evolver-indeterminate {
            animation: none;
            width: 100%;
            background: linear-gradient(
              90deg,
              var(--color-gold),
              var(--color-btc)
            );
            opacity: 0.5;
          }
        }
      `}</style>
    </div>
  );
}
