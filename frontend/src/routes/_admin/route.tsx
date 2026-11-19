// ported from: web/src/app.tsx (route tree and DashboardShell)
import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AppShell } from "@/components/admin/layout/app-shell";
import { ToastProvider } from "@/components/ops/toast";

/**
 * Everything behind sign-in. Route tree (the original react-router tree, plus the clinic screens):
 *   /today /patients /patients/$id                                      clinic operations
 *   /admin/auth                                                         the signed-in account
 *   /admin/agent (/plugins/$name/$page)                                 the agent and the pages its plugins ship
 */
export const Route = createFileRoute("/_admin")({
  component: () => (
    <ToastProvider>
      <AppShell>
        <Outlet />
      </AppShell>
    </ToastProvider>
  ),
});
