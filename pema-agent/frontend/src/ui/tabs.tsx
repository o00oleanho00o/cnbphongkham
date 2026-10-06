"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { cx } from "./classnames";

export type TabItem = {
  id: string;
  label: string;
  /** Shorter label for the segmented control of a phone (`segmentedOnPhone`); defaults to `label`. */
  shortLabel?: string;
  count?: number;
};

const tabId = (idPrefix: string, id: string): string => `${idPrefix}-tab-${id}`;
const panelId = (idPrefix: string, id: string): string => `${idPrefix}-panel-${id}`;

const TAB_CLASS = {
  underline: {
    base: "-mb-px min-h-11 border-b-2 px-3.5 py-2.5 text-body whitespace-nowrap transition-colors lg:min-h-10",
    selected: "border-link font-bold text-link",
    idle: "border-transparent text-ink-soft hover:text-ink",
  },
  pill: {
    base: "min-h-9 rounded-tile px-3 py-1.5 text-small whitespace-nowrap transition-colors",
    selected: "bg-surface font-bold text-link shadow-card",
    idle: "text-ink-soft hover:text-ink",
  },
};

function tabClass(segmented: boolean, selected: boolean): string {
  const look = TAB_CLASS[segmented ? "pill" : "underline"];
  return cx(look.base, selected ? look.selected : look.idle);
}

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
 *
 * `segmented`: the same tabs as a pill control (selected pill raised) at every width, with no bottom rule.
 *
 * `segmentedOnPhone`: below `lg` the same tabs become a segmented control (one row of equal pills that never
 * scrolls, `shortLabel` shown), from `lg` the underline bar. One set of ids either way.
 */
export function Tabs({
  label,
  idPrefix,
  items,
  value,
  onChange,
  segmentedOnPhone = false,
  segmented = false,
}: {
  label: string;
  /** Unique per page; ties each tab to its panel (`TabPanel`). */
  idPrefix: string;
  items: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
  segmentedOnPhone?: boolean;
  /** Segmented control at every width (the shared Inbox: Chờ nhận / Của tôi / Tất cả; the roster: one identity per tab). */
  segmented?: boolean;
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
      className={cx(
        segmented
          ? "mb-4 flex w-fit max-w-full gap-0.5 overflow-x-auto rounded-control border border-line bg-tile p-0.5"
          : "mb-5 flex gap-1 overflow-x-auto border-b border-line",
        segmentedOnPhone &&
          "grid gap-0.5 overflow-visible rounded-control border bg-tile p-0.5 lg:flex lg:gap-1 lg:overflow-x-auto lg:rounded-none lg:border-0 lg:border-b lg:bg-transparent lg:p-0",
      )}
      style={
        segmentedOnPhone
          ? { gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }
          : undefined
      }
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
              tabClass(segmented, selected),
              segmentedOnPhone &&
                "mb-0 min-w-0 rounded-tile px-1 text-small lg:-mb-px lg:rounded-none lg:px-3.5 lg:text-body",
              segmentedOnPhone &&
                selected &&
                "border-transparent bg-surface shadow-card lg:border-link lg:bg-transparent lg:shadow-none",
            )}
          >
            {segmentedOnPhone && item.shortLabel !== undefined ? (
              <>
                <span className="truncate lg:hidden">{item.shortLabel}</span>
                <span className="hidden lg:inline">{item.label}</span>
              </>
            ) : (
              item.label
            )}
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
