import type { ReactNode } from "react";

/** Nothing to show yet: say what is missing and, when possible, offer the one action that fixes it. */
export function EmptyState({
  title,
  hint,
  action,
  icon,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-line bg-surface px-6 py-12 text-center shadow-card">
      {icon !== undefined && (
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-tile bg-brand-50 text-brand-500">
          {icon}
        </div>
      )}
      <p className="text-body-lg font-semibold text-ink">{title}</p>
      {hint !== undefined && (
        <p className="mx-auto mt-1 max-w-md text-body text-ink-soft">{hint}</p>
      )}
      {action !== undefined && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}
