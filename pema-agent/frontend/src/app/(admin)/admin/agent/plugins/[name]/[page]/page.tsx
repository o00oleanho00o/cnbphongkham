"use client";

import { useParams } from "next/navigation";

import { PluginDetailPage } from "@/components/agent/pages/plugin-detail-page";

export default function PluginPageRoute() {
  const { name, page } = useParams<{ name: string; page: string }>();
  return <PluginDetailPage name={decodeURIComponent(name)} pageId={decodeURIComponent(page)} />;
}
