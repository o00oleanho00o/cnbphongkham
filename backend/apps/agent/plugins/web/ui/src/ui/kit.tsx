/**
 * The small kit the dashboard and the plugins' pages share (exposed to plugins as `sdk.ui`), on the Pema tokens.
 * Plugins use these instead of their own buttons and fields so every page looks the same.
 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type Tone = "neutral" | "info" | "success" | "warning" | "danger";

const BUTTON: Record<"primary" | "secondary" | "danger" | "ghost", string> = {
  primary: "bg-brand-500 text-white hover:bg-brand-600",
  secondary: "border border-line bg-surface text-ink hover:bg-tile",
  danger: "border border-danger-line bg-surface text-danger hover:bg-danger-soft",
  ghost: "text-link hover:bg-tile",
};

const TONE: Record<Tone, string> = {
  neutral: "border-line bg-tile text-ink-soft",
  info: "border-info-line bg-info-soft text-info",
  success: "border-success-line bg-success-soft text-success",
  warning: "border-warning-line bg-warning-soft text-warning",
  danger: "border-danger-line bg-danger-soft text-danger",
};

export const FIELD_CLASS =
  "w-full min-h-11 rounded-field border border-line-strong bg-field px-3 py-2 text-body text-ink outline-none " +
  "placeholder:text-ink-soft/60 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 sm:min-h-0";

export function Button({
  variant = "primary",
  busy = false,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof BUTTON; busy?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-control px-4 py-2 text-body font-medium transition-colors disabled:opacity-50 sm:min-h-0 ${BUTTON[variant]} ${className}`}
    >
      {busy ? "…" : null}
      {children}
    </button>
  );
}

export function Card({ title, aside, children }: { title?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-card border border-line bg-surface p-5 shadow-card">
      {(title || aside) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-section font-bold text-heading">{title}</h2>}
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, aside }: { title: string; subtitle?: string; aside?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-title font-bold text-heading">{title}</h1>
        {subtitle && <p className="mt-1 text-small text-ink-soft">{subtitle}</p>}
      </div>
      {aside}
    </header>
  );
}

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
      <span className="mb-1 block text-small font-medium text-ink">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-label text-ink-soft">{hint}</span>}
      {error && <span className="mt-1 block text-label text-danger">{error}</span>}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${FIELD_CLASS} ${props.className ?? ""}`} />;
}

export function Select({
  options,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { options: readonly { value: string; label: string }[] }) {
  return (
    <select {...rest} className={`${FIELD_CLASS} ${rest.className ?? ""}`}>
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
      className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center disabled:opacity-50 sm:h-6 sm:w-10"
    >
      <span className={`h-5 w-9 rounded-pill transition-colors ${checked ? "bg-brand-500" : "bg-ink-soft/40"}`} />
      <span
        className={`absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-pill bg-surface shadow transition-all ${checked ? "left-[calc(50%+2px)]" : "left-[calc(50%-16px)]"}`}
      />
    </button>
  );
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-pill border px-2 py-0.5 text-label font-medium ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function Notice({ tone = "info", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={`rounded-tile border px-3 py-2 text-small ${TONE[tone]}`}>
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-small text-ink-soft">{children}</p>;
}

export const ui = { Button, Card, PageHeader, Field, Input, Select, Toggle, Badge, Notice, Empty, FIELD_CLASS };
export type Kit = typeof ui;
