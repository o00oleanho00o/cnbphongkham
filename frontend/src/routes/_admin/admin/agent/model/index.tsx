import { createFileRoute } from "@tanstack/react-router";

import { ModelPage } from "@/components/agent/pages/model-page";

export const Route = createFileRoute("/_admin/admin/agent/model/")({ component: ModelPage });
