"use client";

// Điều khiển agent: the agent's own pages (overview, chat sessions, trace, model, plugins) as tabs, and one tab for
// each plugin that declares a `section` (the knowledge store). Each plugin's page, and the pages the plugin ships,
// open from the Plugins list (`/admin/agent/plugins/<name>`); the layout installs the plugin SDK once for them. The
// agent answers every call of a role without `admin.agents` with 403.
import type { ReactNode } from "react";

import { AgentPluginsProvider, pluginPageHref, useAgentPlugins } from "@/components/agent/agent-plugins";
import { SubNav, type SubNavItem } from "@/components/agent/sub-nav";
import { pluginHref } from "@/lib/agent/plugins";

const BEFORE_SECTIONS: readonly SubNavItem[] = [
  { href: "/admin/agent/overview", label: "Tổng quan" },
  { href: "/admin/agent/sessions", label: "Phiên chat" },
  { href: "/admin/agent/traces", label: "Trace" },
];

function AgentTabs() {
  const { registered } = useAgentPlugins();
  const sections: SubNavItem[] = [...registered].flatMap(([plugin, contribution]) =>
    contribution.section
      ? [
          {
            href: pluginPageHref(plugin, contribution.section.page),
            label: contribution.section.title,
            within: pluginHref(plugin),
          },
        ]
      : [],
  );
  const plugins: SubNavItem = {
    href: "/admin/agent/plugins",
    label: "Plugins",
    except: sections.flatMap((s) => (s.within ? [s.within] : [])),
  };
  return (
    <SubNav
      label="Trang quản trị agent"
      items={[...BEFORE_SECTIONS, ...sections, { href: "/admin/agent/model", label: "Model" }, plugins]}
    />
  );
}

export default function AgentPluginsLayout({ children }: { children: ReactNode }) {
  return (
    <AgentPluginsProvider>
      <AgentTabs />
      {children}
    </AgentPluginsProvider>
  );
}
