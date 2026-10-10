"use client";

// Tổng quan agent: ported from `plugins/web/ui/src/pages/overview.tsx`, on the clinic web kit (`plugin-kit`).
/** What runs: the chat channels and the plugins' background jobs, with their last error; and a warning while the
 * agent has no model it can call (it starts without one, but then answers nothing). */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { formatCount, type Usage, usageTotals, USAGE_PATH } from "@/lib/agent/activity";
import { agentApi as api } from "@/lib/agent/api";
import { missingModelParts, type ModelShown } from "@/lib/agent/model-status";
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
  const [missing, setMissing] = useState<string[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [c, j, model, used] = await Promise.all([
        api.get<{ channels: Channel[] }>("/v1/admin/channels"),
        api.get<{ jobs: Job[] }>("/v1/admin/jobs"),
        api.get<ModelShown>("/v1/admin/model"),
        api.get<Usage>(`${USAGE_PATH}?days=${USAGE_DAYS}`),
      ]);
      setChannels(c.channels);
      setJobs(j.jobs);
      setMissing(missingModelParts(model));
      setUsage(used);
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
      {missing.length > 0 && (
        <div className="mb-4">
          <Notice tone="warning">
            <b>Chưa cấu hình model AI - agent chưa trả lời được tin nhắn nào.</b> Thiếu{" "}
            {missing.join(", ")}.{" "}
            <Link href="/admin/agent/model" className="font-medium underline underline-offset-2">
              Nhập ở trang Model
            </Link>
          </Notice>
        </div>
      )}
      {usage && usage.days.length > 0 && <UsageCards usage={usage} />}
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

const USAGE_DAYS = 14;

/** Today's turns and tokens, the totals of the fortnight and a bar per day (failed turns in red). */
function UsageCards({ usage }: { usage: Usage }) {
  const today = usage.days[usage.days.length - 1];
  const totals = usageTotals(usage.days);
  const tallest = Math.max(1, ...usage.days.map((day) => day.turns));
  return (
    <div className="mb-4 grid gap-4 sm:grid-cols-3">
      <Card title="Lượt trả lời hôm nay">
        <p className="text-title font-bold text-heading">{formatCount(today?.turns ?? 0)}</p>
        <p className="text-label text-ink-soft">
          {formatCount(totals.turns)} lượt trong {USAGE_DAYS} ngày
          {totals.failed > 0 && `, ${formatCount(totals.failed)} không thành công`}
        </p>
      </Card>
      <Card title="Token hôm nay">
        <p className="text-title font-bold text-heading">
          {formatCount((today?.input_tokens ?? 0) + (today?.output_tokens ?? 0))}
        </p>
        <p className="text-label text-ink-soft">
          {formatCount(totals.tokens)} token trong {USAGE_DAYS} ngày
        </p>
      </Card>
      <Card title={`${USAGE_DAYS} ngày qua`}>
        <div
          role="img"
          aria-label={`Số lượt trả lời mỗi ngày trong ${USAGE_DAYS} ngày qua`}
          className="flex h-16 items-end gap-1"
        >
          {usage.days.map((day) => (
            <div
              key={day.day}
              title={`${day.day}: ${day.turns} lượt${day.failed > 0 ? `, ${day.failed} lỗi` : ""}`}
              className={`min-h-0.5 flex-1 rounded-sm ${day.failed > 0 ? "bg-danger" : "bg-brand-500"}`}
              style={{ height: `${Math.max(3, (day.turns / tallest) * 100)}%` }}
            />
          ))}
        </div>
      </Card>
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
