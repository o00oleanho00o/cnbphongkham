// ported from: web/src/app.tsx (route tree and DashboardShell)
import type { ReactNode } from "react";

import { AppShell } from "@/components/admin/layout/app-shell";
import { ToastProvider } from "@/components/ops/toast";

/**
 * Everything behind sign-in. Route tree (the original react-router tree, plus the clinic screens):
 *   /today /inbox /review /patients /patients/[id] /templates          clinic operations
 *   /admin/overview /threads /contacts /friends /schedules /memory /kb  AI administration, one route per
 *   /admin/accounts /agents (/new, /[id]) /tools /mcp /traces /logs     page of the original dashboard
 *   /admin/tuning (/[group]) /policy /auth
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <AppShell>{children}</AppShell>
    </ToastProvider>
  );
}
