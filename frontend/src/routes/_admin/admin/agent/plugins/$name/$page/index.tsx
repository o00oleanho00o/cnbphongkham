import { createFileRoute } from "@tanstack/react-router";
import { useParams } from "@/lib/navigation";

import { useAgentPlugins } from "@/components/agent/agent-plugins";
import { PluginOrConnectorPage } from "@/components/agent/pages/connector-page";
import { PluginPageHost } from "@/components/agent/plugin-page-host";

function PluginPageRoute() {
  const params = useParams<{ name: string; page: string }>();
  const { registered } = useAgentPlugins();
  const name = decodeURIComponent(params.name);
  const pageId = decodeURIComponent(params.page);
  // The page a plugin shows as a tab of its own (`section`) is drawn without the plugin's name, switch and tabs.
  const isSection = registered.get(name)?.section?.page === pageId;
  if (isSection) return <PluginPageHost plugin={name} pageId={pageId} />;
  return <PluginOrConnectorPage name={name} pageId={pageId} />;
}

export const Route = createFileRoute("/_admin/admin/agent/plugins/$name/$page/")({
  component: PluginPageRoute,
});
