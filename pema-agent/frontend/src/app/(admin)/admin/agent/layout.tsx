"use client";

// Quản trị agent: the agent's own pages (overview, model, plugins) and the admin pages its plugins ship (their browser
// half), hosted in the clinic web. The tabs list both; the agent answers every call of a role without `admin.agents`
// with 403.
import type { ReactNode } from "react";

import { AgentPluginsProvider, useAgentPlugins } from "@/components/agent/agent-plugins";
import { SubNav } from "@/components/care/care-ui";

const OWN_PAGES = [
  { href: "/admin/agent/overview", label: "Tổng quan" },
  { href: "/admin/agent/model", label: "Model" },
  { href: "/admin/agent/plugins", label: "Plugins" },
] as const;

function PluginTabs() {
  const { pages } = useAgentPlugins();
  const several = new Set(pages.map((p) => p.plugin)).size > 1;
  const fromPlugins = pages.map((p) => ({
    href: p.href,
    label: several ? `${p.plugin} · ${p.title}` : p.title,
  }));
  return <SubNav label="Trang quản trị agent" items={[...OWN_PAGES, ...fromPlugins]} />;
}

export default function AgentPluginsLayout({ children }: { children: ReactNode }) {
  return (
    <AgentPluginsProvider>
      <PluginTabs />
      {children}
    </AgentPluginsProvider>
  );
}
