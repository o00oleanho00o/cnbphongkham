import { createFileRoute } from "@tanstack/react-router";
import { OverviewPage } from "@/components/agent/pages/overview-page";

export const Route = createFileRoute("/_admin/admin/agent/overview/")({ component: OverviewPage });
