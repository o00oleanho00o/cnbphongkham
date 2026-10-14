/** Pieces the pages share that the dashboard's kit does not have: a sheet, tabs, chips. */
import { type MouseEvent, type ReactNode, useEffect } from "react";

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

function closeOnBackdrop(event: MouseEvent, onClose: () => void) {
  if (event.target !== event.currentTarget) return;
  onClose();
}

/** A panel that slides in from the right. */
export function Sheet({
  title,
  onClose,
  footer,
  children,
}: {
  title: string;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}) {
  useEscape(onClose);
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-ink/25"
      onMouseDown={(event) => closeOnBackdrop(event, onClose)}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="flex h-full w-full max-w-2xl flex-col border-l border-line bg-surface"
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

/** A small word with a rounded outline: a scope. `onRemove` adds an x. */
export function Chip({ children, onRemove }: { children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-line bg-tile px-2.5 py-0.5 text-label text-ink">
      {children}
      {onRemove && (
        <button type="button" aria-label="Bỏ" onClick={onRemove} className="text-ink-soft hover:text-ink">
          ×
        </button>
      )}
    </span>
  );
}
