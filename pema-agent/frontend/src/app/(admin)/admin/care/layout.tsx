"use client";

// Quản trị agent chăm sóc: kỹ năng và ca trực, số trực 24/24, ma trận ngưỡng, SLA và khung giờ, cảnh báo.
// The tabs only list the pages; each page checks its own permission (a convenience: the backend refuses
// every call of a role without it).
import type { ReactNode } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconBot } from "@/components/admin/shared/dashboard-icons";
import { ADMIN_CARE_ITEMS, SubNav } from "@/components/care/care-ui";

export default function AdminCareLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        icon={IconBot}
        title="Agent chăm sóc"
        subtitle="Người nhận yêu cầu, số trực, ngưỡng độ sâu và thời hạn trả lời"
      />
      <SubNav label="Quản trị agent chăm sóc" items={ADMIN_CARE_ITEMS} />
      {children}
    </div>
  );
}
