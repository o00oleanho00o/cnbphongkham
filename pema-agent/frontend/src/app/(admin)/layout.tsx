// ported from: web/src/app.tsx (route tree and DashboardShell)
import type { ReactNode } from "react";

import { AppShell } from "@/components/admin/layout/app-shell";
import { ToastProvider } from "@/components/ops/toast";

/**
 * Everything behind sign-in. Route tree (the original react-router tree, plus the clinic screens):
 *   /today /inbox /patients /patients/[id]                              clinic operations
 *   /admin/auth                                                         the signed-in account
 *   /admin/agent (/p/[plugin]/[page])                                   the agent and the pages its plugins ship
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <AppShell>{children}</AppShell>
    </ToastProvider>
  );
}
