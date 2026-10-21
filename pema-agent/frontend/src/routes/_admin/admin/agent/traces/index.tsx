import { createFileRoute } from "@tanstack/react-router";
import { TracesPage } from "@/components/agent/pages/traces-page";

export const Route = createFileRoute("/_admin/admin/agent/traces/")({ component: TracesPage });
