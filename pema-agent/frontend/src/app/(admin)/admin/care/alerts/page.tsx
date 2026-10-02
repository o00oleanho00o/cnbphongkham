"use client";

// Cảnh báo của agent chăm sóc: agent bị hạ mức tự chủ, khách không phản hồi nhiều lần, cờ đỏ, dùng số trực.
// A `care.changed` event reloads the list quietly; without the stream it refreshes every 30 seconds.
import Link from "next/link";
import { useCallback } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import { NoAccess } from "@/components/care/care-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { EmptyState, ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { careApi } from "@/lib/care/care-api";
import type { CareAlertKind } from "@/lib/care/care-types";
import { ALERT_KIND_LABEL, knownCodeLabel } from "@/lib/care/labels";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { formatDateTime } from "@/lib/ops/format";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

const LIVE_TYPES: readonly LiveEventType[] = ["care.changed"];
const TONE: Record<CareAlertKind, "red" | "amber" | "blue" | "gray"> = {
  red_flag: "red",
  on_call_used: "amber",
  demotion: "blue",
  unresponsive: "gray",
};

function detailOf(code: string | null | undefined): string {
  const label = code ? knownCodeLabel(code) : null;
  return label ? ` · ${label}` : "";
}

export default function CareAlertsPage() {
  const { can } = useSession();
  if (!can("care.admin")) return <NoAccess what="xem cảnh báo của agent" />;
  return <AlertsContent />;
}

function AlertsContent() {
  const load = useCallback((signal: AbortSignal) => careApi.alerts(signal), []);
  const { data, error, loading, reload, refresh } = useLoad(load);
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });
  return (
    <div>
      <LiveStatus mode={liveMode} />
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && data.items.length === 0 && (
        <EmptyState
          title="Chưa có cảnh báo nào"
          hint="Khi agent bị hạ mức, gặp cờ đỏ hoặc dùng số trực, cảnh báo hiện ở đây."
        />
      )}
      <ul className="space-y-3">
        {data?.items.map((alert) => (
          <li
            key={alert.id}
            className="gc-card flex flex-wrap items-center justify-between gap-2 p-4"
          >
            <div className="min-w-0">
              <Badge tone={TONE[alert.kind]}>{ALERT_KIND_LABEL[alert.kind]}</Badge>
              <p className="mt-1 text-[14px] text-ink">
                {alert.patient_id && alert.patient_name ? (
                  <Link
                    href={`/care/patients/${alert.patient_id}/timeline`}
                    className="font-medium text-brand-500 hover:underline"
                  >
                    {alert.patient_name}
                  </Link>
                ) : (
                  "Toàn hệ thống"
                )}
                {detailOf(alert.code)}
              </p>
            </div>
            <span className="text-[12px] text-ink-soft">{formatDateTime(alert.at)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
