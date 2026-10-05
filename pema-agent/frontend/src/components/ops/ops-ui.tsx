"use client";

// Small building blocks shared by the clinic operation screens. They sit on the same tokens as the ported
// dashboard bits (`ui-bits.tsx`), which stay the source for Badge, TableShell, SectionCard, PageHeader.
import type { ReactNode } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import type { Schemas } from "@/lib/api";
import { PRIORITY_LABEL, RISK_LABEL } from "@/lib/ops/labels";
import { Button } from "@/ui/button";
import { cx } from "@/ui/classnames";

type Tone = "blue" | "gray" | "green" | "red" | "amber";

/** Toggle chip of a filter row; at least 44px high on phones. */
export function FilterChip({
  selected,
  onClick,
  children,
  count,
}: {
  selected: boolean;
  onClick: () => void;
  children: ReactNode;
  count?: number;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onClick}
      className={cx(
        "inline-flex min-h-11 items-center gap-1.5 self-start rounded-pill border px-3.5 text-small font-medium whitespace-nowrap transition-colors lg:min-h-9",
        selected
          ? "border-brand-500 bg-brand-500 text-surface"
          : "border-line bg-surface text-ink-soft hover:bg-tile hover:text-ink",
      )}
    >
      {children}
      {count !== undefined && (
        <span
          className={cx(
            "rounded-pill px-1.5 text-micro",
            selected ? "bg-surface/20" : "bg-tile text-ink-soft",
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

/** A row of chips that scrolls sideways inside itself on a phone instead of wrapping into a wall. */
export function ChipRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="group"
      aria-label={label}
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0"
    >
      {children}
    </div>
  );
}

const PRIORITY_TONE: Record<Schemas["TaskPriority"], Tone> = {
  high: "red",
  normal: "blue",
  low: "gray",
};

export function PriorityBadge({ priority }: { priority: Schemas["TaskPriority"] }) {
  return <Badge tone={PRIORITY_TONE[priority]}>{PRIORITY_LABEL[priority]}</Badge>;
}

const RISK_TONE: Record<Schemas["RiskLevel"], Tone> = {
  normal: "gray",
  attention: "amber",
  red_flag: "red",
};

export function RiskBadge({ risk }: { risk: Schemas["RiskLevel"] }) {
  return <Badge tone={RISK_TONE[risk]}>{RISK_LABEL[risk]}</Badge>;
}

export function Spinner({ label = "Đang tải" }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex justify-center py-10">
      <span className="h-7 w-7 animate-spin rounded-pill border-4 border-brand-200 border-t-brand-500" />
    </div>
  );
}

/** Placeholder rows while the first load runs: the layout does not jump when data arrives. */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-hidden className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-card border border-line bg-tile/40" />
      ))}
    </div>
  );
}

// EmptyState moved to the design kit (src/ui/empty-state.tsx); same props, so screens keep their import.
export { EmptyState } from "@/ui/empty-state";

const NOTICE_TONE: Record<"info" | "warn" | "error" | "success", string> = {
  info: "border-info-line bg-info-soft text-info",
  warn: "border-warning-line bg-warning-soft text-warning",
  error: "border-danger-line bg-danger-soft text-danger",
  success: "border-success-line bg-success-soft text-success",
};

export function Notice({
  tone = "info",
  children,
  action,
}: {
  tone?: "info" | "warn" | "error" | "success";
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "note"}
      className={cx(
        "flex flex-wrap items-center justify-between gap-2 rounded-tile border px-3 py-2 text-small leading-relaxed",
        NOTICE_TONE[tone],
      )}
    >
      <span className="min-w-0 flex-1">{children}</span>
      {action}
    </div>
  );
}

export function RetryNotice({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Notice
      tone="error"
      action={
        <button
          type="button"
          onClick={onRetry}
          className="min-h-9 rounded-control border border-danger-line bg-surface px-3 text-small font-medium text-danger hover:bg-danger-soft"
        >
          Thử lại
        </button>
      }
    >
      {message}
    </Notice>
  );
}

export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = "button",
  form,
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  /** id of the form this button submits when it sits outside it (sheet footer) */
  form?: string;
}) {
  return (
    <Button variant="primary" type={type} form={form} disabled={disabled} onClick={onClick}>
      {children}
    </Button>
  );
}

export function SecondaryButton({
  children,
  disabled,
  onClick,
  type = "button",
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
}) {
  return (
    <Button variant="secondary" type={type} disabled={disabled} onClick={onClick}>
      {children}
    </Button>
  );
}

/** Label + control wrapper used by the forms (the control must carry the matching `id`). */
export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1.5 block text-small font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-label text-ink-soft">{hint}</p>}
    </div>
  );
}
