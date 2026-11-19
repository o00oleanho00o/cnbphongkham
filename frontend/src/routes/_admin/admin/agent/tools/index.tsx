import { createFileRoute } from "@tanstack/react-router";
import { ToolsPage } from "@/components/agent/pages/tools-page";

export const Route = createFileRoute("/_admin/admin/agent/tools/")({ component: ToolsPage });
