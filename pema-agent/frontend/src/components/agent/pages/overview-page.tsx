"use client";

// Tổng quan agent: ported from `plugins/web/ui/src/pages/overview.tsx`, on the clinic web kit (`plugin-kit`).
/** What runs: the chat channels and the plugins' background jobs, with their last error. */
import { useCallback, useEffect, useState } from "react";

import { agentApi as api } from "@/lib/agent/api";
import { Badge, Button, Card, Empty, Notice, PageHeader } from "@/components/agent/plugin-kit";

interface Channel {
  name: string;
  running: boolean;
  error: string | null;
}

interface Job {
  name: string;
  running: boolean;
  error: string | null;
}

export function OverviewPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [c, j] = await Promise.all([
        api.get<{ channels: Channel[] }>("/v1/admin/channels"),
        api.get<{ jobs: Job[] }>("/v1/admin/jobs"),
      ]);
      setChannels(c.channels);
      setJobs(j.jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Tổng quan"
        subtitle="Kênh chat và việc chạy nền của các plugin"
        aside={
          <Button variant="secondary" onClick={() => void load()}>
            Tải lại
          </Button>
        }
      />
      {error && <Notice tone="danger">{error}</Notice>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Kênh chat">
          <StatusList
            items={channels}
            empty="Chưa có kênh nào chạy - bật một plugin kênh (Zalo) ở mục Plugins."
          />
        </Card>
        <Card title="Việc chạy nền">
          <StatusList items={jobs} empty="Không có việc chạy nền." />
        </Card>
      </div>
    </div>
  );
}

function StatusList({ items, empty }: { items: (Channel | Job)[]; empty: string }) {
  if (items.length === 0) return <Empty>{empty}</Empty>;
  return (
    <ul className="divide-y divide-line">
      {items.map((item) => (
        <li key={item.name} className="flex flex-wrap items-center justify-between gap-2 py-2">
          <span className="font-medium break-all">{item.name}</span>
          <Badge tone={item.error ? "danger" : item.running ? "success" : "neutral"}>
            {item.error ? "Lỗi" : item.running ? "Đang chạy" : "Đang dừng"}
          </Badge>
          {item.error && <p className="w-full text-label text-danger">{item.error}</p>}
        </li>
      ))}
    </ul>
  );
}
