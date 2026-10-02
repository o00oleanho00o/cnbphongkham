"use client";

// Yêu cầu đang chờ tôi: the rounds in which the care agent asked a person to take over a conversation. The agent
// decides WHEN a person is needed (skill `handoff`); here staff only answer: Nhận (the conversation becomes
// theirs) or Từ chối (with a reason, optionally naming a colleague). Who is asked, in which order and by when is the
// backend's routing; the list shows it. A `handoff.changed` event (GET /api/v1/events) reloads the list quietly, so
// a request taken by a colleague disappears and a new one appears without a refresh; without the stream the list
// refreshes every 30 seconds.
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconBot } from "@/components/admin/shared/dashboard-icons";
import { DeclineSheet } from "@/components/care/decline-sheet";
import { HandoffCard } from "@/components/care/handoff-card";
import { NoAccess } from "@/components/care/care-ui";
import { LiveStatus } from "@/components/ops/live-status";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage } from "@/lib/api/client";
import { careApi, type HandoffScope } from "@/lib/care/care-api";
import type { HandoffWaiting } from "@/lib/care/care-types";
import { useNow } from "@/lib/care/sla";
import type { LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

const LIVE_TYPES: readonly LiveEventType[] = ["handoff.changed"];

export default function HandoffsPage() {
  const { can } = useSession();
  if (!can("care.read")) return <NoAccess what="xem các yêu cầu chuyển giao" />;
  return <HandoffsContent />;
}

function HandoffsContent() {
  const router = useRouter();
  const toast = useToast();
  const now = useNow();
  const [scope, setScope] = useState<HandoffScope>("mine");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [declining, setDeclining] = useState<HandoffWaiting | null>(null);
  const [declineError, setDeclineError] = useState("");

  const load = useCallback((signal: AbortSignal) => careApi.handoffs(scope, signal), [scope]);
  const { data, error, loading, reload, refresh } = useLoad(load);
  const liveMode = useLiveEvents({ types: LIVE_TYPES, onEvent: refresh, onRefresh: refresh });
  const items = data?.items ?? [];

  function fail(id: string, e: unknown) {
    setErrors((current) => ({ ...current, [id]: errorMessage(e) }));
    // A 409 means somebody was faster: show the list as it is now.
    refresh();
  }

  async function accept(item: HandoffWaiting) {
    setBusyId(item.patient_id);
    setErrors((current) => ({ ...current, [item.patient_id]: "" }));
    try {
      await careApi.accept(item.patient_id);
      toast.push("success", `Bạn đã nhận cuộc trò chuyện của ${item.patient_name}.`);
      router.push(`/care/patients/${item.patient_id}/timeline`);
    } catch (e) {
      fail(item.patient_id, e);
    } finally {
      setBusyId(null);
    }
  }

  async function decline(reason: string, suggestUserId: string | null) {
    if (!declining) return;
    const target = declining;
    setBusyId(target.patient_id);
    setDeclineError("");
    try {
      await careApi.decline(target.patient_id, reason, suggestUserId);
      toast.push("success", "Đã từ chối. Hệ thống chuyển cho người kế tiếp.");
      setDeclining(null);
      refresh();
    } catch (e) {
      setDeclineError(errorMessage(e));
      refresh();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        icon={IconBot}
        title="Yêu cầu đang chờ tôi"
        subtitle="Agent nhờ người nhận khi cuộc trò chuyện vượt mức nó được tự xử lý"
      />
      <LiveStatus mode={liveMode} />
      <div className="mb-4">
        <ChipRow label="Phạm vi">
          <FilterChip selected={scope === "mine"} onClick={() => setScope("mine")}>
            Chờ tôi
          </FilterChip>
          <FilterChip selected={scope === "all"} onClick={() => setScope("all")}>
            Tất cả đang mở
          </FilterChip>
        </ChipRow>
      </div>

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && items.length === 0 && (
        <EmptyState
          title={
            scope === "mine" ? "Không có yêu cầu nào đang chờ bạn" : "Không có yêu cầu nào đang mở"
          }
          hint="Khi agent cần người, yêu cầu hiện ở đây kèm tóm tắt và thời hạn trả lời."
        />
      )}
      <ul className="space-y-3">
        {items.map((item) => (
          <li key={item.patient_id}>
            <HandoffCard
              item={item}
              now={now}
              busy={busyId === item.patient_id}
              error={errors[item.patient_id] ?? ""}
              onAccept={(i) => void accept(i)}
              onDecline={(i) => {
                setDeclineError("");
                setDeclining(i);
              }}
            />
          </li>
        ))}
      </ul>

      {declining && (
        <DeclineSheet
          key={declining.patient_id}
          patientName={declining.patient_name}
          busy={busyId === declining.patient_id}
          error={declineError}
          onClose={() => setDeclining(null)}
          onSubmit={(reason, suggest) => void decline(reason, suggest)}
        />
      )}
    </div>
  );
}
