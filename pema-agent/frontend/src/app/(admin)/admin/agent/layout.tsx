"use client";

// Plugin agent: the admin pages the agent's plugins ship (their browser half), hosted in the clinic web. The tabs list
// the pages the enabled plugins registered; the agent answers every call of a role without `admin.agents` with 403.
import type { ReactNode } from "react";

import { AgentPluginsProvider, useAgentPlugins } from "@/components/agent/agent-plugins";
import { SubNav } from "@/components/care/care-ui";

function PluginTabs() {
  const { pages } = useAgentPlugins();
  if (pages.length === 0) return null;
  const several = new Set(pages.map((p) => p.plugin)).size > 1;
  return (
    <SubNav
      label="Trang của plugin agent"
      items={pages.map((p) => ({
        href: p.href,
        label: several ? `${p.plugin} · ${p.title}` : p.title,
      }))}
    />
  );
}

export default function AgentPluginsLayout({ children }: { children: ReactNode }) {
  return (
    <AgentPluginsProvider>
      <PluginTabs />
      {children}
    </AgentPluginsProvider>
  );
}
