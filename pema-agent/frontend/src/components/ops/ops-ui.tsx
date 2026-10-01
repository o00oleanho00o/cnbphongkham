"use client";

// Small building blocks shared by the clinic operation screens. They sit on the same tokens as the ported
// dashboard bits (`ui-bits.tsx`), which stay the source for Badge, TableShell, SectionCard, PageHeader.
import type { ReactNode } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import type { Schemas } from "@/lib/api";
import { PRIORITY_LABEL, RISK_LABEL } from "@/lib/ops/labels";

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
      className={`inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3.5 text-[13px] font-medium whitespace-nowrap transition-colors lg:min-h-9 ${
        selected
          ? "border-brand-500 bg-brand-500 text-white"
          : "border-line bg-surface text-ink-soft hover:bg-tile hover:text-ink"
      }`}
    >
      {children}
      {count !== undefined && (
        <span
          className={`rounded-full px-1.5 text-[11px] ${selected ? "bg-white/20" : "bg-tile text-ink-soft"}`}
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
      <span className="h-7 w-7 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500" />
    </div>
  );
}

/** Placeholder rows while the first load runs: the layout does not jump when data arrives. */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-hidden className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="gc-card h-24 animate-pulse bg-tile/40" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="gc-card px-6 py-12 text-center">
      <p className="text-[15px] font-semibold text-ink">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-md text-[13px] text-ink-soft">{hint}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

const NOTICE_TONE: Record<"info" | "warn" | "error" | "success", string> = {
  info: "border-brand-100 bg-brand-50 text-brand-700",
  warn: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200",
  error:
    "border-red-100 bg-red-50 text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300",
  success:
    "border-emerald-100 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200",
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
      className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-[13px] leading-relaxed ${NOTICE_TONE[tone]}`}
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
          className="min-h-9 rounded-lg border border-red-200 bg-white px-3 text-[13px] font-medium text-red-700 hover:bg-red-50 dark:border-red-900/50 dark:bg-transparent"
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
    <button
      type={type}
      form={form}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 text-[14px] font-medium text-white hover:bg-brand-600 disabled:opacity-50 lg:min-h-10"
    >
      {children}
    </button>
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
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 text-[14px] font-medium text-ink hover:bg-tile disabled:opacity-50 lg:min-h-10"
    >
      {children}
    </button>
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
      <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-ink">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-[12px] text-ink-soft">{hint}</p>}
    </div>
  );
}
