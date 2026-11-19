import { createFileRoute } from "@tanstack/react-router";
import { SessionsPage } from "@/components/agent/pages/sessions-page";

export const Route = createFileRoute("/_admin/admin/agent/sessions/")({ component: SessionsPage });
