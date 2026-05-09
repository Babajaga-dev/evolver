"use client";

import { useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Modal di conferma sostitutivo del `window.confirm()` nativo.
 *
 * Vantaggi:
 * - Stile consistente col tema medievale (Cinzel + gold/crimson)
 * - Automatable da Chrome MCP / e2e (è in DOM, non un browser native modal)
 * - Escape key chiude, click outside chiude
 * - Accessible (role=dialog + aria-modal)
 */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Conferma",
  cancelLabel = "Annulla",
  destructive = false,
  onConfirm,
  onCancel,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center px-4"
      style={{ background: "rgba(8, 2, 16, 0.85)", backdropFilter: "blur(4px)" }}
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md border border-[--color-gold]/60 bg-[--color-surface-card] px-6 py-6"
        onClick={(e) => e.stopPropagation()}
        style={{
          boxShadow: "0 0 24px rgba(197, 160, 89, 0.15)",
        }}
      >
        <p
          className="mb-1 text-[10px] uppercase tracking-[0.4em]"
          style={{
            fontFamily: "var(--font-serif)",
            color: destructive
              ? "var(--color-crimson, #e63946)"
              : "var(--color-gold)",
          }}
        >
          {destructive ? "Action destructive" : "Confirmation required"}
        </p>
        <h2
          id="confirm-dialog-title"
          className="mb-3 text-xl"
          style={{
            fontFamily: "var(--font-serif)",
            letterSpacing: "0.05em",
          }}
        >
          {title}
        </h2>
        <p className="mb-6 text-sm text-[--color-text-secondary]">{message}</p>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="border border-[--color-surface-border] px-4 py-2 text-xs uppercase tracking-[0.2em] text-[--color-text-secondary] hover:text-[--color-text-primary]"
            style={{ fontFamily: "var(--font-serif)" }}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="px-4 py-2 text-xs uppercase tracking-[0.25em]"
            style={{
              fontFamily: "var(--font-serif)",
              background: destructive ? "#8b1a1a" : "#f7931a",
              color: destructive ? "#f0ede8" : "#080210",
              border: `1px solid ${destructive ? "#8b1a1a" : "#f7931a"}`,
            }}
            data-testid="confirm-dialog-confirm"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
