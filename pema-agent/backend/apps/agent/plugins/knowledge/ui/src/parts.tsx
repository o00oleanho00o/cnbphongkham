/** Pieces the pages share that the dashboard's kit does not have: a sheet, a dialog, tabs, chips, a progress bar. */
import { type ReactNode, useEffect } from "react";

import type { Tone } from "./logic";
import { ui } from "./sdk";

export function useEscape(onClose: () => void) {
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);
}

/** A panel that slides in from the right; `wide` for the add-a-source flow. */
export function Sheet({
  title,
  onClose,
  footer,
  wide = false,
  children,
}: {
  title: string;
  onClose: () => void;
  footer?: ReactNode;
  wide?: boolean;
  children: ReactNode;
}) {
  useEscape(onClose);
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-ink/25"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex h-full w-full flex-col border-l border-line bg-surface ${wide ? "max-w-3xl" : "max-w-md"}`}
      >
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="min-w-0 text-section font-bold break-words text-heading">{title}</h2>
          <ui.Button variant="secondary" onClick={onClose}>
            Đóng
          </ui.Button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="border-t border-line px-5 py-4">{footer}</div>}
      </div>
    </div>
  );
}

/** A small centred question with its buttons; `children` are the buttons. */
export function ConfirmDialog({
  title,
  onClose,
  actions,
  children,
}: {
  title: string;
  onClose: () => void;
  actions: ReactNode;
  children: ReactNode;
}) {
  useEscape(onClose);
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/25 p-4"
      onMouseDown={(event) => event.target === event.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-card border border-line bg-surface p-6 shadow-card"
      >
        <h2 className="mb-2 text-section font-bold break-words text-heading">{title}</h2>
        <div className="mb-4 text-body text-ink-soft">{children}</div>
        <div className="flex flex-wrap justify-end gap-2">{actions}</div>
      </div>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3 rounded-tile border border-line p-4">
      <p className="text-micro font-semibold tracking-wider text-ink-soft uppercase">{title}</p>
      {children}
    </div>
  );
}

export function Switch({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>
        <span className="block text-small font-medium text-ink">{label}</span>
        {hint && <span className="block text-label text-ink-soft">{hint}</span>}
      </span>
      <ui.Toggle checked={checked} label={label} onChange={onChange} />
    </div>
  );
}

export interface TabItem<Id extends string> {
  id: Id;
  label: string;
}

export function Tabs<Id extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: readonly TabItem<Id>[];
  value: Id;
  onChange: (id: Id) => void;
}) {
  return (
    <div role="tablist" aria-label={label} className="mb-4 flex gap-1 overflow-x-auto border-b border-line">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={item.id === value}
          onClick={() => onChange(item.id)}
          className={`-mb-px inline-flex min-h-11 items-center border-b-2 px-3.5 text-body whitespace-nowrap ${
            item.id === value ? "border-link font-bold text-link" : "border-transparent text-ink-soft hover:text-ink"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** A small word with a rounded outline: a service, an alias. `onRemove` adds an x. */
export function Chip({ children, onRemove }: { children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-surface-soft px-2.5 py-0.5 text-label text-ink">
      {children}
      {onRemove && (
        <button type="button" aria-label="Bỏ" onClick={onRemove} className="text-ink-soft hover:text-ink">
          ×
        </button>
      )}
    </span>
  );
}

export function ProgressBar({ percent, label }: { percent: number; label: string }) {
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      className="h-1.5 w-full overflow-hidden rounded-full bg-line"
    >
      <div className="h-full bg-link" style={{ width: `${percent}%` }} />
    </div>
  );
}

export function Stat({ label, value, tone = "neutral" }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <div className="rounded-tile border border-line bg-surface px-4 py-3">
      <p className="text-label text-ink-soft">{label}</p>
      <p className={`text-section font-bold ${tone === "danger" ? "text-danger" : "text-heading"}`}>{value}</p>
    </div>
  );
}
