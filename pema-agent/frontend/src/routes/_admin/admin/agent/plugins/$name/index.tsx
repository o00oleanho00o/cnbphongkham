import { createFileRoute } from "@tanstack/react-router";
import { useParams } from "@/lib/navigation";

import { PluginDetailPage } from "@/components/agent/pages/plugin-detail-page";

function PluginRoute() {
  const { name } = useParams<{ name: string }>();
  return <PluginDetailPage name={decodeURIComponent(name)} />;
}

export const Route = createFileRoute("/_admin/admin/agent/plugins/$name/")({
  component: PluginRoute,
});
