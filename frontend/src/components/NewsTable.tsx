"use client";

import type { NewsItem } from "@/lib/api";

interface Props {
  items: NewsItem[];
  loading?: boolean;
}

/**
 * Tabella news scorate con sentiment + event_type + assets.
 *
 * Mobile-first: stack di card. Desktop: tabella.
 */
export function NewsTable({ items, loading }: Props) {
  if (loading && items.length === 0) {
    return (
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-8 text-center font-mono text-sm text-[--color-text-muted]">
        Loading news...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="border border-[--color-surface-border] bg-[--color-surface-card] p-8 text-center font-mono text-sm text-[--color-text-muted]">
        Nessuna news. Premi <span className="text-[--color-gold]">Refresh</span> per
        ingerire dai feed RSS, poi <span className="text-[--color-gold]">Score</span>{" "}
        per arricchire con Claude.
      </div>
    );
  }

  return (
    <div
      className="border border-[--color-surface-border] bg-[--color-surface-card]"
      style={{ opacity: loading ? 0.7 : 1, transition: "opacity 200ms" }}
    >
      {/* Desktop header */}
      <div
        className="hidden border-b border-[--color-surface-border] px-4 py-2 md:grid md:grid-cols-[100px_140px_120px_1fr_80px_80px] md:gap-4"
        style={{
          fontFamily: "var(--font-serif)",
          fontSize: 10,
          textTransform: "uppercase",
          letterSpacing: "0.2em",
          color: "var(--color-gold)",
        }}
      >
        <span>When</span>
        <span>Source · Type</span>
        <span>Assets</span>
        <span>Title</span>
        <span style={{ textAlign: "right" }}>Sentiment</span>
        <span style={{ textAlign: "right" }}>Confidence</span>
      </div>

      {items.map((it) => (
        <NewsRow key={it.id} item={it} />
      ))}
    </div>
  );
}

function NewsRow({ item }: { item: NewsItem }) {
  const score = item.score;
  const published = new Date(item.published_at);

  return (
    <div className="border-b border-[--color-surface-border]/60 px-4 py-3 md:grid md:grid-cols-[100px_140px_120px_1fr_80px_80px] md:items-start md:gap-4 md:py-2">
      {/* When */}
      <div className="flex items-center justify-between md:block">
        <span
          className="text-xs text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-mono)" }}
          title={published.toISOString()}
        >
          {formatRelative(published)}
        </span>
        {/* Mobile: badges row */}
        <span className="md:hidden">
          {score && <SentimentChip sentiment={score.sentiment_score} />}
        </span>
      </div>

      {/* Source · Type */}
      <div className="mt-1 flex flex-wrap items-center gap-2 md:mt-0">
        <span
          className="text-xs uppercase text-[--color-text-secondary]"
          style={{
            fontFamily: "var(--font-serif)",
            letterSpacing: "0.15em",
          }}
        >
          {item.source}
        </span>
        {score && <EventTypeBadge eventType={score.event_type} />}
      </div>

      {/* Assets */}
      <div className="mt-1 flex flex-wrap gap-1 md:mt-0">
        {score?.assets_mentioned.length ? (
          score.assets_mentioned.map((a) => <AssetChip key={a} asset={a} />)
        ) : (
          <span className="text-xs text-[--color-text-muted]">—</span>
        )}
      </div>

      {/* Title (link) */}
      <div className="mt-2 md:mt-0">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="text-sm text-[--color-text-primary] hover:text-[--color-gold]"
          style={{
            fontFamily: "var(--font-body, var(--font-serif))",
            lineHeight: 1.4,
          }}
        >
          {item.title}
        </a>
        {score?.reasoning && (
          <p
            className="mt-1 text-xs italic text-[--color-text-muted]"
            style={{ lineHeight: 1.5 }}
          >
            {score.reasoning}
          </p>
        )}
      </div>

      {/* Sentiment (desktop) */}
      <div className="hidden md:flex md:justify-end">
        {score ? (
          <SentimentChip sentiment={score.sentiment_score} />
        ) : (
          <span className="text-xs text-[--color-text-muted]">—</span>
        )}
      </div>

      {/* Confidence */}
      <div className="mt-1 hidden text-right md:mt-0 md:block">
        {score ? (
          <span
            className="text-xs text-[--color-text-secondary]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {(score.confidence * 100).toFixed(0)}%
          </span>
        ) : (
          <span className="text-xs text-[--color-text-muted]">—</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chips
// ---------------------------------------------------------------------------

function AssetChip({ asset }: { asset: string }) {
  return (
    <span
      className="border border-[--color-gold]/40 bg-[--color-surface-elevated] px-1.5 py-0.5 text-[10px]"
      style={{
        fontFamily: "var(--font-mono)",
        color: "var(--color-gold)",
        letterSpacing: "0.1em",
      }}
    >
      {asset}
    </span>
  );
}

const EVENT_COLORS: Record<string, string> = {
  hack: "var(--color-crimson, #e63946)",
  regulation: "#7799ff",
  partnership: "#00ff99",
  adoption: "#00ff99",
  technology: "#bb77ff",
  opinion: "var(--color-text-muted)",
  market: "var(--color-gold)",
  macro: "#f7931a",
  other: "var(--color-text-secondary)",
};

function EventTypeBadge({ eventType }: { eventType: string }) {
  const color = EVENT_COLORS[eventType] ?? EVENT_COLORS.other;
  return (
    <span
      className="px-1.5 py-0.5 text-[10px]"
      style={{
        fontFamily: "var(--font-serif)",
        textTransform: "uppercase",
        letterSpacing: "0.15em",
        border: `1px solid ${color}`,
        color,
        background: "transparent",
      }}
    >
      {eventType}
    </span>
  );
}

function SentimentChip({ sentiment }: { sentiment: number }) {
  const color =
    sentiment > 0.1
      ? "#00ff99"
      : sentiment < -0.1
        ? "#e63946"
        : "var(--color-text-muted)";
  const sign = sentiment > 0 ? "+" : "";
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 text-xs"
      style={{
        fontFamily: "var(--font-mono)",
        color,
        border: `1px solid ${color}`,
        letterSpacing: "0.05em",
      }}
    >
      {sign}
      {sentiment.toFixed(2)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelative(d: Date): string {
  const diff = Date.now() - d.getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const days = Math.floor(h / 24);
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
