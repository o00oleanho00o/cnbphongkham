// Navigation of the single Pema dashboard. Order and labels of the first three sections are the old Pema
// Clinic Web sidebar (prototype/shared/clinic.js `nav`: dashboard, today, schedule, patients, followups,
// studio; "Quản lý": resources, services, cashier, finance; "Phân tích": ask, guide). The last section is the
// agent: one entry, its pages are tabs.
//
// `needs` is "any of": an entry is SHOWN when the BE's permission list for the role contains one of
// them. This is a convenience only; every request is authorized by the BE.
//
// `planned: true` marks an old screen whose page is built in a later step of package U (U2..U7). It is
// listed in its old position but is not a link yet; the step that builds the page removes the flag.
// Its `needs` is a placeholder until that step sets the real permission.
import type { ReactNode, SVGProps } from "react";

import { IconGrid, IconHeart, IconUsers } from "@/components/admin/shared/dashboard-icons";
import { IconClipboardCheck, IconInbox, IconUser } from "@/components/admin/shared/ops-icons";
import type { Permission } from "@/lib/session/session-context";
import {
  IconBanknote,
  IconBook,
  IconCalendar,
  IconImages,
  IconPuzzle,
  IconReceipt,
  IconSparkles,
  IconStethoscope,
} from "@/ui/icons";

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
    title: "Không gian làm việc",
    items: [
      {
        to: "/dashboard",
        label: "Tổng quan",
        icon: IconGrid,
        needs: ["appointment.read", "crm.task.read"],
      },
      {
        to: "/today",
        label: "Hôm nay",
        tabLabel: "Việc",
        icon: IconCalendar,
        needs: ["crm.task.read"],
        tab: true,
      },
      {
        to: "/schedule",
        label: "Điều phối lịch",
        icon: IconClipboardCheck,
        needs: ["appointment.read"],
      },
      {
        to: "/patients",
        label: "Tìm bệnh nhân",
        tabLabel: "Hồ sơ",
        icon: IconUser,
        needs: ["patient.read"],
        tab: true,
      },
      {
        to: "/inbox",
        label: "Theo dõi",
        tabLabel: "Inbox",
        icon: IconInbox,
        needs: ["conversation.read"],
        tab: true,
      },
      {
        to: "/studio",
        label: "Ảnh trước / sau",
        icon: IconImages,
        needs: ["patient.read_360"],
      },
    ],
  },
  {
    title: "Quản lý",
    items: [
      {
        to: "/resources",
        label: "Bác sĩ & phòng",
        icon: IconStethoscope,
        needs: ["appointment.read"],
      },
      {
        to: "/services",
        label: "Dịch vụ",
        icon: IconHeart,
        needs: ["appointment.read"],
      },
      {
        to: "/cashier",
        label: "Thu ngân",
        icon: IconReceipt,
        needs: ["order.read", "order.write"],
        aliases: ["/orders"],
      },
      {
        to: "/finance",
        label: "Tài chính & tiền thủ thuật",
        icon: IconBanknote,
        needs: ["finance.read", "finance.read_own"],
      },
    ],
  },
  {
    title: "Phân tích",
    items: [
      { to: "/ask", label: "Hỏi Pema", icon: IconSparkles, needs: ["kb.read"] },
      { to: "/guide", label: "Hướng dẫn", icon: IconBook, needs: ["kb.read"] },
      // Not an old sidebar entry: the CRM01 groups and rules that /today, /dashboard and Patient 360 do not show.
      { to: "/crm", label: "Vòng đời khách hàng", icon: IconUsers, needs: ["crm.task.read"] },
    ],
  },
  {
    title: "Agent",
    items: [
      // One entry for the whole agent: its own pages (overview, model, plugins) and the pages each plugin ships
      // (Zalo accounts, contacts, friends, groups, bridge) are tabs under /admin/agent.
      { to: "/admin/agent", label: "Điều khiển agent", icon: IconPuzzle, needs: ["admin.agents"] },
    ],
  },
];

/** Sections filtered by the permissions the BE granted; empty sections disappear. */
export function visibleSections(can: (needs: readonly Permission[]) => boolean): NavSection[] {
  return NAV_SECTIONS.map((s) => ({ ...s, items: s.items.filter((i) => can(i.needs)) })).filter(
    (s) => s.items.length > 0,
  );
}

/**
 * First screen a role can open, used after sign-in and for `/`. Planned screens have no page yet. The old Clinic
 * Web opened the dashboard for everybody except the care role, whose home was the CSKH queue
 * (`staff-context.js` `home()`); the care role is the one that resolves tasks but may not edit the schedule.
 */
export function homeFor(can: (needs: readonly Permission[]) => boolean): string {
  if (can(["crm.task.resolve"]) && !can(["appointment.write"]) && can(["crm.task.read"])) {
    return "/today";
  }
  // The accountant ("Đối soát & thu ngân") opens on the cashier, as in the old web's `home()`: it collects and
  // reads the clinic finance but has no schedule, so no role with `appointment.read` lands here.
  if (can(["finance.collect"]) && can(["finance.read"]) && !can(["appointment.read"])) {
    return "/cashier";
  }
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
