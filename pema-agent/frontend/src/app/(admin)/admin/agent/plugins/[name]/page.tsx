"use client";

import { useParams } from "next/navigation";

import { PluginDetailPage } from "@/components/agent/pages/plugin-detail-page";

export default function PluginRoute() {
  const { name } = useParams<{ name: string }>();
  return <PluginDetailPage name={decodeURIComponent(name)} />;
}
