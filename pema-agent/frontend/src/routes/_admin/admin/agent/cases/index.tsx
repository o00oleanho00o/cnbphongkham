import { createFileRoute } from "@tanstack/react-router";
import { CasesPage } from "@/components/agent/pages/cases-page";

export const Route = createFileRoute("/_admin/admin/agent/cases/")({ component: CasesPage });
