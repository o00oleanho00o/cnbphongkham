import type { ReactNode } from "react";

import { cx } from "./classnames";

/**
 * Metric tile of the old dashboard (`.metric-card`): small label, big value in the heading colour, one
 * line of context. `tone` only colours the note, so a red value never replaces the words.
 */
export function Tile({
  label,
  value,
  note,
  tone = "neutral",
  icon,
  className,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger";
  icon?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cx(
        "min-w-0 rounded-card border border-line bg-surface p-4 shadow-card sm:px-5 sm:py-[19px]",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 text-label text-ink-soft">
        <span className="truncate">{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-metric leading-tight font-bold text-heading">{value}</div>
      {note !== undefined && <div className={cx("mt-1 text-label", NOTE_TONE[tone])}>{note}</div>}
    </div>
  );
}

const NOTE_TONE: Record<"neutral" | "success" | "warning" | "danger", string> = {
  neutral: "text-ink-soft",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};
