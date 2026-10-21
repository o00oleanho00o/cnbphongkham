import { createFileRoute, Outlet } from "@tanstack/react-router";

import { FinanceLayout } from "@/components/finance/finance-layout";

export const Route = createFileRoute("/_admin/finance")({
  component: () => (
    <FinanceLayout>
      <Outlet />
    </FinanceLayout>
  ),
});
