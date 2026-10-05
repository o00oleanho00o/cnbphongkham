// Navigation of the single Pema dashboard. Order and labels of the first three sections are the old Pema
// Clinic Web sidebar (prototype/shared/clinic.js `nav`: dashboard, today, schedule, patients, followups,
// studio; "Quản lý": resources, services, cashier, finance; "Phân tích": ask, guide). The next three
// sections group what this app added: Zalo & CSKH, the care agent, and the AI administration ported from
// zalo-agent (its SECTIONS array in layout/sidebar-nav.tsx).
//
// `needs` is "any of": an entry is SHOWN when the BE's permission list for the role contains one of
// them. This is a convenience only; every request is authorized by the BE.
//
// `planned: true` marks an old screen whose page is built in a later step of package U (U2..U7). It is
// listed in its old position but is not a link yet; the step that builds the page removes the flag.
// Its `needs` is a placeholder until that step sets the real permission.
import type { ReactNode, SVGProps } from "react";

import {
  IconBolt,
  IconBot,
  IconBrain,
  IconChat,
  IconClock,
  IconCpu,
  IconDatabase,
  IconFileText,
  IconGear,
  IconGlobe,
  IconGrid,
  IconHeart,
  IconSignal,
  IconSliders,
  IconUsers,
} from "@/components/admin/shared/dashboard-icons";
import {
  IconClipboardCheck,
  IconIdBadge,
  IconInbox,
  IconShieldCheck,
  IconUser,
} from "@/components/admin/shared/ops-icons";
import type { Permission } from "@/lib/session/session-context";
import {
  IconBanknote,
  IconBook,
  IconCalendar,
  IconImages,
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
    title: "Zalo & CSKH",
    items: [
      {
        to: "/review",
        label: "Hàng đợi duyệt",
        tabLabel: "Duyệt",
        icon: IconShieldCheck,
        needs: ["review.read"],
        tab: true,
      },
      { to: "/templates", label: "Mẫu tin", icon: IconFileText, needs: ["kb.read"] },
    ],
  },
  {
    title: "Care agent",
    items: [
      {
        to: "/care/handoffs",
        label: "Yêu cầu chuyển giao",
        tabLabel: "Chờ tôi",
        icon: IconBot,
        needs: ["care.read"],
        tab: true,
      },
      {
        to: "/admin/care/staff",
        label: "Kỹ năng và ca trực",
        icon: IconUsers,
        needs: ["care.admin"],
      },
      { to: "/admin/care/on-call", label: "Số trực 24/24", icon: IconClock, needs: ["care.admin"] },
      {
        to: "/admin/care/matrix",
        label: "Ma trận ngưỡng",
        icon: IconSliders,
        needs: ["care.matrix"],
      },
      {
        to: "/admin/care/timing",
        label: "SLA và khung giờ",
        icon: IconGear,
        needs: ["care.admin"],
      },
      { to: "/admin/care/alerts", label: "Cảnh báo agent", icon: IconBolt, needs: ["care.admin"] },
    ],
  },
  {
    title: "Quản trị agent",
    items: [
      { to: "/admin/overview", label: "Tổng quan AI", icon: IconGrid, needs: ["admin.usage"] },
      { to: "/admin/traces", label: "Trace agent", icon: IconCpu, needs: ["admin.usage"] },
      { to: "/admin/threads", label: "Phiên chat", icon: IconChat, needs: ["admin.agents"] },
      { to: "/admin/contacts", label: "Danh bạ", icon: IconUsers, needs: ["admin.agents"] },
      { to: "/admin/friends", label: "Bạn bè", icon: IconHeart, needs: ["admin.accounts"] },
      {
        to: "/admin/schedules",
        label: "Lịch tự động",
        icon: IconClock,
        needs: ["admin.schedules"],
      },
      { to: "/admin/memory", label: "Trí nhớ", icon: IconBrain, needs: ["admin.agents"] },
      { to: "/admin/kb", label: "Kho tri thức", icon: IconFileText, needs: ["kb.read"] },
      {
        to: "/admin/accounts",
        label: "Tài khoản Zalo",
        icon: IconSignal,
        needs: ["admin.accounts"],
      },
      { to: "/admin/users", label: "Nhân viên", icon: IconIdBadge, needs: ["admin.users.read"] },
      { to: "/admin/agents", label: "Agents", icon: IconBot, needs: ["admin.agents"] },
      { to: "/admin/tools", label: "Tools", icon: IconBolt, needs: ["admin.tools"] },
      { to: "/admin/mcp", label: "MCP", icon: IconGlobe, needs: ["admin.mcp"] },
      {
        to: "/admin/policy",
        label: "Hồ sơ chính sách",
        icon: IconShieldCheck,
        needs: ["admin.policy"],
      },
      { to: "/admin/logs", label: "Logs", icon: IconDatabase, needs: ["admin.logs"] },
      // Nhà cung cấp LLM là một nhóm trong trang Cấu hình (/admin/tuning/providers), như bản gốc.
      { to: "/admin/tuning", label: "Mô hình & cấu hình", icon: IconGear, needs: ["admin.model"] },
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
