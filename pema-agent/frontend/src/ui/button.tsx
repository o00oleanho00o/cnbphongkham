import type { ButtonHTMLAttributes } from "react";

import { cx } from "./classnames";

export type ButtonVariant = "primary" | "secondary" | "danger" | "danger-solid" | "quiet";

const BASE =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-control px-3.5 text-small font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-10";

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  primary:
    "border border-brand-500 bg-brand-500 text-surface hover:border-brand-600 hover:bg-brand-600",
  secondary: "border border-line-strong bg-surface text-ink hover:bg-tile",
  danger: "border border-danger-line bg-surface text-danger hover:bg-danger-soft",
  "danger-solid": "border border-danger bg-danger text-surface hover:opacity-90",
  quiet: "border border-transparent px-0 text-link hover:underline",
};

/** Class names of a button, for a link or a label that has to look like one. */
export function buttonClass(variant: ButtonVariant = "primary", extra?: string): string {
  return cx(BASE, VARIANT_CLASS[variant], extra);
}

/**
 * Button of the old web (`.btn`, `.btn-primary`, `.btn-danger`, `.btn-quiet`): radius 10, 40px high (44px on a
 * phone), 12px semibold label. `type` defaults to "button" so a button inside a form never submits by accident.
 */
export function Button({
  variant = "primary",
  type = "button",
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button type={type} className={buttonClass(variant, className)} {...rest} />;
}
