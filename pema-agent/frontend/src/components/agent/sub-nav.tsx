// Tabs between the pages of one area (the agent's own pages and the pages its plugins ship); scrolls sideways
// inside itself on a phone.
import { Link } from "@/lib/link";
import { usePathname } from "@/lib/navigation";

import { cx } from "@/ui/classnames";

/** `exact`: active only on its own address, not on the pages below it (an overview tab next to its sub-pages).
 * `within`: active on every address that starts with this path (a tab that opens one page of an area).
 * `except`: paths below `href` that belong to another tab. */
export type SubNavItem = {
  href: string;
  label: string;
  exact?: boolean;
  within?: string;
  except?: readonly string[];
};

export function SubNav({ label, items }: { label: string; items: readonly SubNavItem[] }) {
  const pathname = usePathname();
  return (
    <nav
      aria-label={label}
      className="-mx-4 mb-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0"
    >
      {items.map((item) => {
        const under = (path: string) => pathname === path || pathname.startsWith(`${path}/`);
        const active = item.within
          ? under(item.within)
          : (pathname === item.href || (!item.exact && pathname.startsWith(`${item.href}/`))) &&
            !item.except?.some(under);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "-mb-px inline-flex min-h-11 items-center border-b-2 px-3.5 text-body whitespace-nowrap lg:min-h-10",
              active
                ? "border-link font-bold text-link"
                : "border-transparent text-ink-soft hover:text-ink",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
