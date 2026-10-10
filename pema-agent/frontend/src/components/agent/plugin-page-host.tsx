"use client";

// One page an agent plugin ships (`/admin/agent/plugins/<plugin>/<page>`): the component its script registered, or
// why it cannot be shown (still loading, script failed, plugin off, no such page).
import Link from "next/link";

import { PluginsProblem, useAgentPlugins } from "@/components/agent/agent-plugins";
import { RetryNotice } from "@/components/ops/ops-ui";
import { pluginHref } from "@/lib/agent/plugins";
import { buttonClass } from "@/ui/button";
import { EmptyState } from "@/ui/empty-state";

export function PluginPageHost({ plugin, pageId }: { plugin: string; pageId: string }) {
  const { state, retry, registered } = useAgentPlugins();
  const contribution = registered.get(plugin);
  const page = contribution?.pages?.find((p) => p.id === pageId);

  if (page) {
    const PluginPage = page.component;
    return <PluginPage key={`${plugin}/${pageId}`} />;
  }
  if (state.kind !== "ready") return <PluginsProblem state={state} retry={retry} />;
  if (state.failed.includes(plugin)) {
    return <RetryNotice message={`Không tải được trang của plugin ${plugin}.`} onRetry={retry} />;
  }
  return (
    <EmptyState
      title="Không tìm thấy trang này"
      hint={
        contribution
          ? `Plugin ${plugin} không có trang "${pageId}".`
          : `Plugin ${plugin} chưa bật hoặc không có trang quản trị.`
      }
      action={
        <Link href={pluginHref(plugin)} className={buttonClass("secondary")}>
          Về trang plugin {plugin}
        </Link>
      }
    />
  );
}
