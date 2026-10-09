"use client";

// One page of an agent plugin (`/admin/agent/p/<plugin>/<page>`): the component the plugin's script registered.
import Link from "next/link";
import { useParams } from "next/navigation";

import { PluginsProblem, useAgentPlugins } from "@/components/agent/agent-plugins";
import { RetryNotice } from "@/components/ops/ops-ui";
import { buttonClass } from "@/ui/button";
import { EmptyState } from "@/ui/empty-state";

export default function PluginPageHost() {
  const { plugin, page: pageId } = useParams<{ plugin: string; page: string }>();
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
        <Link href="/admin/agent" className={buttonClass("secondary")}>
          Về trang plugin agent
        </Link>
      }
    />
  );
}
