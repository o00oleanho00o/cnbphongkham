import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AgentPluginsLayout } from "@/components/agent/agent-layout";

export const Route = createFileRoute("/_admin/admin/agent")({
  component: () => (
    <AgentPluginsLayout>
      <Outlet />
    </AgentPluginsLayout>
  ),
});
