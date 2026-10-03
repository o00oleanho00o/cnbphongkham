import type { ReactNode } from "react";

import { cx } from "./classnames";

export type BadgeTone = "neutral" | "brand" | "info" | "success" | "warning" | "danger";

const TONE_CLASS: Record<BadgeTone, { chip: string; dot: string }> = {
  neutral: { chip: "border-line bg-tile text-ink-soft", dot: "bg-ink-soft" },
  brand: { chip: "border-brand-100 bg-brand-50 text-brand-700", dot: "bg-brand-500" },
  info: { chip: "border-info-line bg-info-soft text-info", dot: "bg-info" },
  success: { chip: "border-success-line bg-success-soft text-success", dot: "bg-success" },
  warning: { chip: "border-warning-line bg-warning-soft text-warning", dot: "bg-warning" },
  danger: { chip: "border-danger-line bg-danger-soft text-danger", dot: "bg-danger" },
};

/**
 * Status chip. The text is always the status: colour only supports it (readable without colour vision).
 * Tones map to the status tokens of tokens.css, which carry their own dark values.
 */
export function Badge({
  tone = "neutral",
  dot = true,
  children,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
}) {
  const { chip, dot: dotClass } = TONE_CLASS[tone];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-label font-medium",
        chip,
      )}
    >
      {dot && <span aria-hidden className={cx("h-1.5 w-1.5 rounded-pill", dotClass)} />}
      {children}
    </span>
  );
}
