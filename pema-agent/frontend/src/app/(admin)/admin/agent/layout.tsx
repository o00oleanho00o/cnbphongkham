"use client";

// Điều khiển agent: the agent's own pages (overview, chat sessions, trace, model, plugins) as tabs. Each plugin's page, and the pages the
// plugin ships, open from the Plugins list (`/admin/agent/plugins/<name>`); the layout installs the plugin SDK once
// for them. The agent answers every call of a role without `admin.agents` with 403.
import type { ReactNode } from "react";

import { AgentPluginsProvider } from "@/components/agent/agent-plugins";
import { SubNav } from "@/components/agent/sub-nav";

const OWN_PAGES = [
  { href: "/admin/agent/overview", label: "Tổng quan" },
  { href: "/admin/agent/sessions", label: "Phiên chat" },
  { href: "/admin/agent/traces", label: "Trace" },
  { href: "/admin/agent/model", label: "Model" },
  { href: "/admin/agent/plugins", label: "Plugins" },
] as const;

export default function AgentPluginsLayout({ children }: { children: ReactNode }) {
  return (
    <AgentPluginsProvider>
      <SubNav label="Trang quản trị agent" items={OWN_PAGES} />
      {children}
    </AgentPluginsProvider>
  );
}
