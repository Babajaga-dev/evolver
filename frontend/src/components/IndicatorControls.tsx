"use client";

import { useState } from "react";

import type { IndicatorInfo } from "@/lib/api";

export interface ActiveIndicator {
  /** UUID interno per gestire più istanze dello stesso indicator. */
  uid: string;
  /** ID indicatore es. "rsi", "macd". */
  id: string;
  /** Etichetta human-readable es. "RSI". */
  label: string;
  /** Tipo: overlay sul prezzo o pannello separato. */
  kind: "overlay" | "panel";
  /** Parametri scelti dall'utente. */
  params: Record<string, number | string>;
}

interface Props {
  registry: IndicatorInfo[];
  active: ActiveIndicator[];
  onAdd: (next: ActiveIndicator) => void;
  onRemove: (uid: string) => void;
}

export function IndicatorControls({
  registry,
  active,
  onAdd,
  onRemove,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <section className="mb-6 border border-[--color-surface-border] bg-[--color-surface-card] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2
          className="text-xs uppercase tracking-[0.3em] text-[--color-text-secondary]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          Indicators
        </h2>
        <button
          onClick={() => setPickerOpen((v) => !v)}
          className="border border-[--color-gold] px-3 py-1 font-mono text-xs uppercase tracking-[0.2em] text-[--color-gold] transition-colors hover:bg-[--color-surface-elevated]"
        >
          {pickerOpen ? "× chiudi" : "+ aggiungi"}
        </button>
      </div>

      {/* Active list */}
      {active.length === 0 ? (
        <p className="font-mono text-xs text-[--color-text-muted]">
          Nessun indicatore attivo. Premi "+ aggiungi" per iniziare.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {active.map((ind) => (
            <li
              key={ind.uid}
              className="flex items-center justify-between border border-[--color-surface-border]/40 bg-[--color-surface] px-3 py-2 font-mono text-xs"
            >
              <span>
                <span
                  className="text-[--color-gold]"
                  style={{ fontFamily: "var(--font-serif)" }}
                >
                  {ind.label}
                </span>{" "}
                <span className="text-[--color-text-secondary]">
                  {formatParams(ind.params)}
                </span>{" "}
                <span className="text-[--color-text-muted]">· {ind.kind}</span>
              </span>
              <button
                onClick={() => onRemove(ind.uid)}
                className="text-[--color-text-muted] hover:text-[--color-crimson]"
                aria-label="rimuovi"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Picker */}
      {pickerOpen && (
        <div className="mt-4 border-t border-[--color-surface-border] pt-4">
          <div className="grid gap-2 md:grid-cols-2">
            {registry.map((info) => (
              <IndicatorPickerItem
                key={info.id}
                info={info}
                onAdd={(params) => {
                  onAdd({
                    uid: crypto.randomUUID(),
                    id: info.id,
                    label: info.label,
                    kind: info.kind,
                    params,
                  });
                  setPickerOpen(false);
                }}
              />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function IndicatorPickerItem({
  info,
  onAdd,
}: {
  info: IndicatorInfo;
  onAdd: (params: Record<string, number | string>) => void;
}) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(info.params.map((p) => [p.name, String(p.default)])),
  );

  const handleAdd = () => {
    const parsed: Record<string, number | string> = {};
    for (const p of info.params) {
      const raw = values[p.name];
      parsed[p.name] = p.type === "int"
        ? parseInt(raw, 10)
        : p.type === "float"
          ? parseFloat(raw)
          : raw;
    }
    onAdd(parsed);
  };

  return (
    <div className="border border-[--color-surface-border] p-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <span
          className="font-mono text-xs uppercase tracking-[0.2em] text-[--color-gold]"
          style={{ fontFamily: "var(--font-serif)" }}
        >
          {info.label}
        </span>
        <span
          className="font-mono text-xs text-[--color-text-muted]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {info.kind}
        </span>
      </button>
      {info.description && (
        <p className="mt-1 text-xs text-[--color-text-secondary]">
          {info.description}
        </p>
      )}
      {open && (
        <div className="mt-3 space-y-2">
          {info.params.map((p) => (
            <label key={p.name} className="block">
              <span className="block font-mono text-[10px] uppercase tracking-[0.2em] text-[--color-text-secondary]">
                {p.name}
                {p.min !== null && p.min !== undefined && (
                  <span className="ml-2 text-[--color-text-muted]">
                    [{p.min} – {p.max}]
                  </span>
                )}
              </span>
              <input
                type={p.type === "str" ? "text" : "number"}
                step={p.type === "float" ? "0.1" : "1"}
                min={p.min ?? undefined}
                max={p.max ?? undefined}
                value={values[p.name] ?? ""}
                onChange={(e) =>
                  setValues((v) => ({ ...v, [p.name]: e.target.value }))
                }
                className="mt-1 w-full rounded-none border border-[--color-surface-border] bg-[--color-surface] px-2 py-1 font-mono text-xs text-[--color-text-primary] focus:border-[--color-gold] focus:outline-none"
              />
            </label>
          ))}
          <button
            onClick={handleAdd}
            className="mt-2 w-full border border-[--color-btc] bg-transparent px-3 py-1.5 font-mono text-xs uppercase tracking-[0.2em] text-[--color-btc] hover:bg-[--color-surface-elevated]"
          >
            ◆ aggiungi
          </button>
        </div>
      )}
    </div>
  );
}

function formatParams(params: Record<string, number | string>): string {
  const flat = Object.entries(params)
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  return flat ? `(${flat})` : "";
}
