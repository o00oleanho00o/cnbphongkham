import { createFileRoute } from "@tanstack/react-router";
import { PluginsPage } from "@/components/agent/pages/plugins-page";

export const Route = createFileRoute("/_admin/admin/agent/plugins/")({ component: PluginsPage });
