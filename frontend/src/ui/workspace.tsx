import type { ReactNode } from "react";

import { cx } from "./classnames";

/**
 * Page body layout of the old web (workspace-layout.css):
 *  - `split` (default): main column plus an optional `aside` column. One column below 1280px; from 1280px
 *    two columns (main : aside = 1.8fr : 1fr, aside at least 360px) as the Patient 360 and schedule screens.
 *  - `cards`: a grid of equal cards (doctors, rooms, services): 1 column on a phone, 2 from `sm`, 3 from
 *    1280px, 4 from 1600px.
 * Children use `min-w-0` so long Vietnamese names and tables never push the page wider than the viewport.
 */
export function Workspace({
  layout = "split",
  aside,
  className,
  children,
}: {
  layout?: "split" | "cards";
  aside?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  if (layout === "cards") {
    return (
      <div
        className={cx(
          "grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 wide:grid-cols-4 wide:gap-5",
          className,
        )}
      >
        {children}
      </div>
    );
  }
  const hasAside = aside !== undefined;
  return (
    <div
      className={cx(
        "grid grid-cols-1 items-start gap-4 wide:gap-5",
        hasAside && "xl:grid-cols-[minmax(0,1.8fr)_minmax(var(--layout-aside-w),1fr)]",
        className,
      )}
    >
      <div className="min-w-0">{children}</div>
      {hasAside && <aside className="min-w-0">{aside}</aside>}
    </div>
  );
}

/** Title row of a page: heading + subtitle on the left, actions on the right. */
export function PageHeading({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3 wide:mb-6">
      <div className="min-w-0">
        <h1 className="text-title font-bold text-heading sm:text-page">{title}</h1>
        {subtitle !== undefined && <p className="mt-1 text-body text-ink-soft">{subtitle}</p>}
      </div>
      {actions !== undefined && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
