"use client";

// `sdk.ui` of the plugin SDK (plan C): the agent dashboard's kit (`plugins/web/ui/src/ui/kit.tsx`), same names and
// props, drawn with this app's kit so plugin pages look like the rest of the clinic web. Where a prop does not fit
// the app's component (a ReactNode title, a label that wraps its control, the small inline empty line) the piece
// is a thin adapter on the same tokens.
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

import { ToggleKnob } from "@/components/admin/shared/ui-bits";
import { Notice as AppNotice } from "@/components/ops/ops-ui";
import { Badge as AppBadge } from "@/ui/badge";
import { Button as AppButton, type ButtonVariant } from "@/ui/button";
import { Card as AppCard } from "@/ui/card";
import { cx } from "@/ui/classnames";
import { FIELD_CONTROL_CLASS } from "@/ui/field";
import { PageHeading } from "@/ui/workspace";

export type KitTone = "neutral" | "info" | "success" | "warning" | "danger";
export type KitButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const BUTTON_VARIANT: Record<KitButtonVariant, ButtonVariant> = {
  primary: "primary",
  secondary: "secondary",
  danger: "danger",
  ghost: "quiet",
};

const NOTICE_TONE: Record<KitTone, "info" | "warn" | "error" | "success"> = {
  neutral: "info",
  info: "info",
  success: "success",
  warning: "warn",
  danger: "error",
};

export const FIELD_CLASS = FIELD_CONTROL_CLASS;

export function Button({
  variant = "primary",
  busy = false,
  disabled,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: KitButtonVariant; busy?: boolean }) {
  return (
    <AppButton
      {...rest}
      variant={BUTTON_VARIANT[variant]}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? "…" : null}
      {children}
    </AppButton>
  );
}

export function Card({
  title,
  aside,
  children,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const hasHeader = Boolean(title) || Boolean(aside);
  return (
    <AppCard>
      {hasHeader && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {Boolean(title) && <h2 className="text-body-lg font-bold text-heading">{title}</h2>}
          </div>
          {aside}
        </header>
      )}
      {children}
    </AppCard>
  );
}

export function PageHeader({
  title,
  subtitle,
  aside,
}: {
  title: string;
  subtitle?: string;
  aside?: ReactNode;
}) {
  return <PageHeading title={title} subtitle={subtitle} actions={aside} />;
}

/** The label wraps its control: plugin pages pass the control as children, not as a render prop. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-label font-semibold text-ink-soft">{label}</span>
      {children}
      {Boolean(hint) && !error && (
        <span className="mt-1 block text-label text-ink-soft">{hint}</span>
      )}
      {error && (
        <span role="alert" className="mt-1 block text-label text-danger">
          {error}
        </span>
      )}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(FIELD_CLASS, props.className)} />;
}

export function Select({
  options,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: readonly { value: string; label: string }[];
}) {
  return (
    <select {...rest} className={cx(FIELD_CLASS, rest.className)}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-control disabled:opacity-50 sm:h-auto sm:w-auto"
    >
      <ToggleKnob on={checked} />
    </button>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: KitTone; children: ReactNode }) {
  return <AppBadge tone={tone}>{children}</AppBadge>;
}

export function Notice({ tone = "info", children }: { tone?: KitTone; children: ReactNode }) {
  return <AppNotice tone={NOTICE_TONE[tone]}>{children}</AppNotice>;
}

/** The short "nothing here" line inside a card (the app's `EmptyState` is a card of its own). */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-body text-ink-soft">{children}</p>;
}

export const pluginKit = {
  Button,
  Card,
  PageHeader,
  Field,
  Input,
  Select,
  Toggle,
  Badge,
  Notice,
  Empty,
  FIELD_CLASS,
};
export type Kit = typeof pluginKit;
