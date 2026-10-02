// Navigation of the single Pema dashboard: clinic operations first, then the AI administration ported
// from the zalo-agent dashboard (its SECTIONS array in layout/sidebar-nav.tsx).
//
// `needs` is "any of": an entry is SHOWN when the BE's permission list for the role contains one of
// them. This is a convenience only; every request is authorized by the BE.
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
};

export type NavSection = { title: string; items: NavItem[] };

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Vận hành",
    items: [
      {
        to: "/today",
        label: "Việc hôm nay",
        tabLabel: "Việc",
        icon: IconClipboardCheck,
        needs: ["crm.task.read"],
        tab: true,
      },
      {
        to: "/inbox",
        label: "Inbox",
        icon: IconInbox,
        needs: ["conversation.read"],
        tab: true,
      },
      {
        to: "/review",
        label: "Hàng đợi duyệt AI",
        tabLabel: "Duyệt",
        icon: IconShieldCheck,
        needs: ["review.read"],
        tab: true,
      },
      {
        to: "/patients",
        label: "Hồ sơ bệnh nhân",
        tabLabel: "Hồ sơ",
        icon: IconUser,
        needs: ["patient.read"],
        tab: true,
      },
      {
        to: "/templates",
        label: "Tin nhắn mẫu đã duyệt",
        icon: IconFileText,
        needs: ["kb.read"],
      },
    ],
  },
  {
    title: "Tổng quan AI",
    items: [
      { to: "/admin/overview", label: "Tổng quan", icon: IconGrid, needs: ["admin.usage"] },
      { to: "/admin/traces", label: "Trace agent", icon: IconCpu, needs: ["admin.usage"] },
    ],
  },
  {
    title: "Hội thoại AI",
    items: [
      { to: "/admin/threads", label: "Phiên chat", icon: IconChat, needs: ["admin.agents"] },
      { to: "/admin/contacts", label: "Danh bạ", icon: IconUsers, needs: ["admin.agents"] },
      { to: "/admin/friends", label: "Bạn bè", icon: IconHeart, needs: ["admin.accounts"] },
      {
        to: "/admin/schedules",
        label: "Lịch tự động",
        icon: IconClock,
        needs: ["admin.schedules"],
      },
    ],
  },
  {
    title: "Dữ liệu",
    items: [
      { to: "/admin/memory", label: "Trí nhớ", icon: IconBrain, needs: ["admin.agents"] },
      { to: "/admin/kb", label: "Kho tri thức", icon: IconFileText, needs: ["kb.read"] },
    ],
  },
  {
    title: "Hệ thống",
    items: [
      {
        to: "/admin/accounts",
        label: "Tài khoản Zalo",
        icon: IconSignal,
        needs: ["admin.accounts"],
      },
      {
        to: "/admin/users",
        label: "Nhân viên",
        icon: IconIdBadge,
        needs: ["admin.users.read"],
      },
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

/** First screen a role can open, used after sign-in and for `/`. */
export function homeFor(can: (needs: readonly Permission[]) => boolean): string {
  for (const s of NAV_SECTIONS) {
    for (const i of s.items) if (can(i.needs)) return i.to;
  }
  return "/login";
}

export function isActivePath(pathname: string, to: string): boolean {
  return pathname === to || pathname.startsWith(`${to}/`);
}
