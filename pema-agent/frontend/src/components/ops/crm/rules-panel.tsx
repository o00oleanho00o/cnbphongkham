"use client";

// "Quy tắc tự động" of `/crm` (old CRM01 `protocol` card, "Protocol chăm sóc mẫu"): the rules that turn clinic data
// into staff tasks, as text (`GET /api/v1/crm/rules`). Read only: a rule only creates a task for a person unless
// the clinic chose otherwise, and a message to a patient still waits for review.
import { useCallback } from "react";

import { ListSkeleton, Notice, PriorityBadge, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { SEND_MODE_LABEL } from "@/lib/ops/crm-overview-view";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Card } from "@/ui/card";

export function RulesPanel() {
  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/crm/rules", { signal })),
    [],
  );
  const { data, error, loading, reload } = useLoad(load);

  if (error) return <RetryNotice message={error} onRetry={reload} />;
  if (loading && !data) return <ListSkeleton rows={3} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <Notice>
        Ngưỡng và nội dung là mẫu cần chủ phòng khám duyệt trước khi dùng thật. Hệ thống chỉ tạo
        việc cho nhân viên, không tự gửi tin hoặc tự duyệt y khoa.
      </Notice>
      <ol className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.map((rule) => (
          <li key={rule.id}>
            <Card padded={false} className="h-full px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-body font-bold text-heading">{rule.name}</h3>
                <Badge tone={rule.active ? "success" : "neutral"}>
                  {rule.active ? "Đang bật" : "Đang tắt"}
                </Badge>
              </div>
              <p className="mt-1.5 text-body text-ink">{rule.suggested_action}</p>
              <p className="mt-1.5 text-label text-ink-soft">
                {rule.trigger} → sau {rule.delay_days} ngày → tạo việc
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <PriorityBadge priority={rule.priority} />
                <Badge tone="neutral" dot={false}>
                  {SEND_MODE_LABEL[rule.send_mode ?? "staff_task"]}
                </Badge>
              </div>
            </Card>
          </li>
        ))}
      </ol>
    </div>
  );
}
