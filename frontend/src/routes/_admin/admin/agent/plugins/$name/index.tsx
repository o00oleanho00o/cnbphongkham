import { createFileRoute } from "@tanstack/react-router";
import { useParams } from "@/lib/navigation";

import { PluginOrConnectorPage } from "@/components/agent/pages/connector-page";

function PluginRoute() {
  const { name } = useParams<{ name: string }>();
  return <PluginOrConnectorPage name={decodeURIComponent(name)} />;
}

export const Route = createFileRoute("/_admin/admin/agent/plugins/$name/")({
  component: PluginRoute,
});
