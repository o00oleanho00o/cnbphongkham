// ported from: web/src/app.tsx (route tree and DashboardShell)
import type { ReactNode } from "react";

import { AppShell } from "@/components/admin/layout/app-shell";
import { ToastProvider } from "@/components/ops/toast";

/**
 * Everything behind sign-in. Route tree (the original react-router tree, plus the clinic screens):
 *   /today /inbox /review /patients /patients/[id] /templates          clinic operations
 *   /admin/kb /logs /users /auth                                  clinic and knowledge administration
 *   /admin/agent (/p/[plugin]/[page])                                   pages the agent's plugins ship
 */
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <AppShell>{children}</AppShell>
    </ToastProvider>
  );
}
