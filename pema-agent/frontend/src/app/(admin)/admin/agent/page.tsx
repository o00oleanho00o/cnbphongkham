"use client";

// `/admin/agent` opens the first page a plugin registered, or says that no enabled plugin has one.
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { PluginsProblem, useAgentPlugins } from "@/components/agent/agent-plugins";
import { Notice, Spinner } from "@/components/ops/ops-ui";
import { EmptyState } from "@/ui/empty-state";

export default function AgentPluginsIndex() {
  const { state, retry, pages } = useAgentPlugins();
  const router = useRouter();
  const first = state.kind === "ready" ? pages[0]?.href : undefined;

  useEffect(() => {
    if (first) router.replace(first);
  }, [first, router]);

  if (state.kind !== "ready") return <PluginsProblem state={state} retry={retry} />;
  if (first) return <Spinner label="Đang mở trang plugin" />;
  return (
    <div className="space-y-4">
      {state.failed.length > 0 && (
        <Notice tone="error">Không tải được trang của plugin: {state.failed.join(", ")}.</Notice>
      )}
      <EmptyState
        title="Chưa có plugin nào có trang quản trị"
        hint="Bật một plugin có trang quản trị (ví dụ Zalo) ở dịch vụ agent rồi mở lại mục này."
      />
    </div>
  );
}
