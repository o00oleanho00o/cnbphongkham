"use client";

// `/admin/agent` opens the overview, the first page of the agent's own pages.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ops/ops-ui";

export default function AgentIndex() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/admin/agent/overview");
  }, [router]);

  return <Spinner label="Đang mở tổng quan agent" />;
}
