"use client";

// Small pieces shared by the care supervision and administration screens: badges worded from the backend's
// codes, the "no access" state, and the sub-navigation between the pages of one patient or of the admin area.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import { Notice } from "@/components/ops/ops-ui";
import type { CareControlState, CareDepth, CareLevel, CareUrgency } from "@/lib/care/care-types";
import { CONTROL_LABEL, DEPTH_LABEL, LEVEL_LABEL, URGENCY_LABEL } from "@/lib/care/labels";

const DEPTH_TONE: Record<CareDepth, "gray" | "blue" | "amber" | "red"> = {
  D1: "gray",
  D2: "blue",
  D3: "amber",
  D4: "red",
  D5: "red",
};

export function DepthBadge({ depth }: { depth: CareDepth }) {
  return <Badge tone={DEPTH_TONE[depth]}>{DEPTH_LABEL[depth]}</Badge>;
}

export function UrgencyBadge({ urgency }: { urgency: CareUrgency }) {
  return <Badge tone={urgency === "urgent" ? "red" : "gray"}>{URGENCY_LABEL[urgency]}</Badge>;
}

const CONTROL_TONE: Record<CareControlState, "green" | "amber" | "blue"> = {
  AUTO: "green",
  HANDOFF_ROUTING: "amber",
  STAFF: "blue",
};

export function ControlBadge({ state }: { state: CareControlState }) {
  return <Badge tone={CONTROL_TONE[state]}>{CONTROL_LABEL[state]}</Badge>;
}

export function LevelBadge({ level }: { level: CareLevel }) {
  return <Badge tone={level === "L0" ? "gray" : "blue"}>{LEVEL_LABEL[level]}</Badge>;
}

/** The badge of the matrix and the timing: the numbers are defaults until a doctor approves them. */
export function ApprovalBadge({ pending }: { pending: boolean }) {
  return pending ? (
    <Badge tone="amber">Chờ bác sĩ duyệt</Badge>
  ) : (
    <Badge tone="green">Bác sĩ đã duyệt</Badge>
  );
}

export function NoAccess({ what }: { what: string }) {
  return (
    <Notice tone="warn">
      Vai trò của bạn không có quyền {what}. Nếu cần, hãy nhờ chủ phòng khám hoặc quản lý.
    </Notice>
  );
}

export type SubNavItem = { href: string; label: string };

/** Tabs between the pages of one area; scrolls sideways inside itself on a phone. */
export function SubNav({ label, items }: { label: string; items: readonly SubNavItem[] }) {
  const pathname = usePathname();
  return (
    <nav
      aria-label={label}
      className="-mx-4 mb-4 flex gap-1 overflow-x-auto border-b border-line px-4 sm:mx-0 sm:px-0"
    >
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`-mb-px inline-flex min-h-11 items-center border-b-2 px-3 text-[14px] font-medium whitespace-nowrap ${
              active
                ? "border-brand-500 text-brand-500"
                : "border-transparent text-ink-soft hover:text-ink"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function patientCareItems(patientId: string): SubNavItem[] {
  const base = `/care/patients/${patientId}`;
  return [
    { href: `${base}/timeline`, label: "Dòng thời gian" },
    { href: `${base}/release`, label: "Trả lại cho agent" },
    { href: `${base}/tell-agent`, label: "Nói với agent" },
  ];
}

export const ADMIN_CARE_ITEMS: readonly SubNavItem[] = [
  { href: "/admin/care/staff", label: "Kỹ năng và ca trực" },
  { href: "/admin/care/on-call", label: "Số trực 24/24" },
  { href: "/admin/care/matrix", label: "Ma trận ngưỡng" },
  { href: "/admin/care/timing", label: "SLA và khung giờ" },
  { href: "/admin/care/alerts", label: "Cảnh báo" },
];

export function Labelled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-ink-soft">{label}</dt>
      <dd className="mt-0.5 text-[14px] text-ink">{children}</dd>
    </div>
  );
}
