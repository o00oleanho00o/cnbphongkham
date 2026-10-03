import type { ReactNode } from "react";

import { cx } from "./classnames";

/**
 * Panel of the old web (`.panel`): thin border, radius 14, very light shadow. `title` adds the header row
 * (title + optional subtitle on the left, `aside` on the right). Use `padded={false}` for a table inside.
 */
export function Card({
  title,
  subtitle,
  aside,
  padded = true,
  className,
  children,
}: {
  title?: string;
  subtitle?: string;
  aside?: ReactNode;
  padded?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const hasHeader = title !== undefined || aside !== undefined;
  return (
    <section
      className={cx(
        "min-w-0 rounded-card border border-line bg-surface shadow-card",
        padded && "p-4 sm:p-5",
        className,
      )}
    >
      {hasHeader && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title !== undefined && (
              <h2 className="text-body-lg font-bold text-heading">{title}</h2>
            )}
            {subtitle !== undefined && (
              <p className="mt-0.5 text-label text-ink-soft">{subtitle}</p>
            )}
          </div>
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}
