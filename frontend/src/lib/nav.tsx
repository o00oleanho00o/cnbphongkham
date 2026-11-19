// Navigation of the agent dashboard: one entry, the agent's pages and the pages its plugins ship are tabs under it.
//
// `needs` is "any of": an entry is SHOWN when the permission list of the signed-in account contains one of them
// (an agent login has them all). This is a convenience only; every request is authorized by the agent.
import type { ReactNode, SVGProps } from "react";

import type { Permission } from "@/lib/session/session-context";
import { IconPuzzle } from "@/ui/icons";

export type IconFn = (p: SVGProps<SVGSVGElement> & { size?: number }) => ReactNode;

export type NavItem = {
  to: string;
  label: string;
  icon: IconFn;
  needs: readonly Permission[];
  /** Shown in the bottom tab bar on phones (the daily CSKH work). */
  tab?: boolean;
  /** Short label for the bottom tab bar. */
  tabLabel?: string;
  /** Old screen whose page is not built yet: shown in place, not clickable. */
  planned?: boolean;
  /** Other paths that belong to this entry (the order review and print pages belong to "Thu ngân"). */
  aliases?: readonly string[];
};

export type NavSection = { title: string; items: NavItem[] };

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Agent",
    items: [{ to: "/admin/agent", label: "Điều khiển agent", icon: IconPuzzle, needs: ["admin.agents"] }],
  },
];

/** Sections filtered by the permissions the BE granted; empty sections disappear. */
export function visibleSections(can: (needs: readonly Permission[]) => boolean): NavSection[] {
  return NAV_SECTIONS.map((s) => ({ ...s, items: s.items.filter((i) => can(i.needs)) })).filter(
    (s) => s.items.length > 0,
  );
}

/** First screen after sign-in and for `/`. */
export function homeFor(can: (needs: readonly Permission[]) => boolean): string {
  const first = NAV_SECTIONS.flatMap((s) => s.items).find((i) => !i.planned && can(i.needs));
  return first?.to ?? "/login";
}

export function isActivePath(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}

/** The entry is the page itself, a page below it, or one of its aliases. */
export function isItemActive(pathname: string, item: NavItem): boolean {
  return [item.to, ...(item.aliases ?? [])].some((to) => isActivePath(pathname, to));
}

/** The most specific item whose path contains `pathname`: gives the page its title in the top bar. */
export function currentNavItem(pathname: string): NavItem | undefined {
  return NAV_SECTIONS.flatMap((s) => s.items)
    .filter((i) => isItemActive(pathname, i))
    .toSorted((a, b) => b.to.length - a.to.length)[0];
}
