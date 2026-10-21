// `/admin/agent` opens the overview, the first page of the agent's own pages.
import { createFileRoute } from "@tanstack/react-router";
import { useRouter } from "@/lib/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ops/ops-ui";

function AgentIndex() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/agent/overview");
  }, [router]);

  return <Spinner label="Đang mở tổng quan agent" />;
}

export const Route = createFileRoute("/_admin/admin/agent/")({ component: AgentIndex });
