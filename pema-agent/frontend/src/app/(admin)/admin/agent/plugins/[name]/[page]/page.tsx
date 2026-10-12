"use client";

import { useParams } from "next/navigation";

import { useAgentPlugins } from "@/components/agent/agent-plugins";
import { PluginDetailPage } from "@/components/agent/pages/plugin-detail-page";
import { PluginPageHost } from "@/components/agent/plugin-page-host";

export default function PluginPageRoute() {
  const params = useParams<{ name: string; page: string }>();
  const { registered } = useAgentPlugins();
  const name = decodeURIComponent(params.name);
  const pageId = decodeURIComponent(params.page);
  // The page a plugin shows as a tab of its own (`section`) is drawn without the plugin's name, switch and tabs.
  const isSection = registered.get(name)?.section?.page === pageId;
  if (isSection) return <PluginPageHost plugin={name} pageId={pageId} />;
  return <PluginDetailPage name={name} pageId={pageId} />;
}
