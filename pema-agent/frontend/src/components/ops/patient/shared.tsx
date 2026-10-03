"use client";

// Small pieces the Patient 360 tabs share.
import type { ReactNode } from "react";

import { cx } from "@/ui/classnames";
import { FIELD_CONTROL_CLASS } from "@/ui/field";

export function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-label text-ink-soft">{label}</dt>
      <dd className="text-body font-medium break-words text-ink">{value}</dd>
    </div>
  );
}

export function Muted({ children }: { children: ReactNode }) {
  return <p className="text-small text-ink-soft">{children}</p>;
}

/** Textarea look of the kit's fields, with room for a few lines. */
export const TEXTAREA_CLASS = cx(FIELD_CONTROL_CLASS, "min-h-24 resize-y");

/** A sentence that blocks the form, announced to assistive technology. */
export function FormError({ message }: { message: string }) {
  if (message === "") return null;
  return (
    <p role="alert" className="mt-2 text-small text-danger">
      {message}
    </p>
  );
}

/** Two columns from `sm`, one on a phone: the layout of a form row of the old web (`.two-col-form`). */
export function TwoCol({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">{children}</div>;
}
