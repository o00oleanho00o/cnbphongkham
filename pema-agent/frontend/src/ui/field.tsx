"use client";

import { useId, type ReactNode } from "react";

import { cx } from "./classnames";

/** Shared look of text inputs, selects and textareas (old `.field input`: radius 9, tinted fill). */
export const FIELD_CONTROL_CLASS =
  "w-full rounded-field border border-line-strong bg-field px-3 py-2 text-body-lg text-ink outline-none placeholder:text-ink-soft/60 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 disabled:opacity-60 aria-[invalid=true]:border-danger";

export type FieldControlProps = {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": boolean | undefined;
};

/**
 * Label + control + hint/error. The control comes in as a render prop so the label's `for`, the hint and
 * the error message are wired to it without each screen repeating ids. Errors are announced (role=alert).
 */
export function Field({
  label,
  hint,
  error,
  required = false,
  className,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: (control: FieldControlProps) => ReactNode;
}) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy =
    [hint === undefined ? "" : hintId, error === undefined ? "" : errorId]
      .filter(Boolean)
      .join(" ") || undefined;
  return (
    <div className={cx("mb-3.5", className)}>
      <label htmlFor={id} className="mb-1.5 block text-label font-semibold text-ink-soft">
        {label}
        {required && (
          <span aria-hidden className="ml-0.5 text-danger">
            *
          </span>
        )}
      </label>
      {children({
        id,
        "aria-describedby": describedBy,
        "aria-invalid": error === undefined ? undefined : true,
      })}
      {hint !== undefined && (
        <p id={hintId} className="mt-1 text-label text-ink-soft">
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} role="alert" className="mt-1 text-label text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
