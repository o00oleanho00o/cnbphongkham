"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { cx } from "./classnames";

export type TabItem = { id: string; label: string; count?: number };

const tabId = (idPrefix: string, id: string): string => `${idPrefix}-tab-${id}`;
const panelId = (idPrefix: string, id: string): string => `${idPrefix}-panel-${id}`;

/** Index of the tab a key moves to, or null when the key is not a tab-navigation key. */
export function targetTabIndex(key: string, current: number, count: number): number | null {
  const moves: Record<string, number> = {
    ArrowRight: (current + 1) % count,
    ArrowLeft: (current - 1 + count) % count,
    Home: 0,
    End: count - 1,
  };
  return moves[key] ?? null;
}

/**
 * Tab bar of the old web (`.tabbar`, the Patient 360 tabs): underline on the active tab, scrolls sideways
 * inside itself on a phone. Arrow keys, Home and End move between tabs (roving tabindex).
 */
export function Tabs({
  label,
  idPrefix,
  items,
  value,
  onChange,
}: {
  label: string;
  /** Unique per page; ties each tab to its panel (`TabPanel`). */
  idPrefix: string;
  items: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>): void {
    const current = items.findIndex((i) => i.id === value);
    const next = targetTabIndex(e.key, current, items.length);
    const item = next === null ? undefined : items[next];
    if (item === undefined) return;
    e.preventDefault();
    onChange(item.id);
    refs.current[item.id]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="mb-5 flex gap-1 overflow-x-auto border-b border-line"
    >
      {items.map((item) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[item.id] = el;
            }}
            id={tabId(idPrefix, item.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(idPrefix, item.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            className={cx(
              "-mb-px min-h-11 border-b-2 px-3.5 py-2.5 text-body whitespace-nowrap transition-colors lg:min-h-10",
              selected
                ? "border-link font-bold text-link"
                : "border-transparent text-ink-soft hover:text-ink",
            )}
          >
            {item.label}
            {item.count !== undefined && (
              <span className="ml-1.5 rounded-pill bg-tile px-1.5 text-eyebrow text-ink-soft">
                {item.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Content of one tab; renders nothing while another tab is selected. */
export function TabPanel({
  idPrefix,
  id,
  value,
  children,
}: {
  idPrefix: string;
  id: string;
  value: string;
  children: ReactNode;
}) {
  if (id !== value) return null;
  return (
    <div role="tabpanel" id={panelId(idPrefix, id)} aria-labelledby={tabId(idPrefix, id)}>
      {children}
    </div>
  );
}
