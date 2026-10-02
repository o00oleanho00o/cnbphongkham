"use client";

// The timeline of one patient's care agent: the state of the conversation and the agent's level, the round that is
// open (why a person was asked), drafts waiting for a person, reminders held back while a person has the
// conversation (with the prepared text to send by hand), what the agent did, and what it remembers. Everything shown
// comes from `GET /api/v1/care/patients/{id}/timeline`; the codes are worded in `lib/care/labels.ts`.
import Link from "next/link";
import { useState } from "react";

import { Badge, SectionCard } from "@/components/admin/shared/ui-bits";
import { DepthBadge, Labelled, UrgencyBadge } from "@/components/care/care-ui";
import { SecondaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { PatientCareTimeline, TimelineEntry } from "@/lib/care/care-types";
import {
  ENTRY_KIND_LABEL,
  LEVEL_LABEL,
  MEMORY_SOURCE_LABEL,
  REVIEW_KIND_SHORT,
  codeLabel,
  reasonLabel,
  skillLabel,
} from "@/lib/care/labels";
import { slaState } from "@/lib/care/sla";
import { formatDateTime } from "@/lib/ops/format";
import { copyText } from "@/lib/ops/clipboard";

const ENTRY_TONE: Record<TimelineEntry["kind"], "green" | "blue" | "amber" | "gray"> = {
  sent: "green",
  reviewed: "blue",
  paused: "amber",
  control: "gray",
  autonomy: "blue",
};

export function TimelineView({ data, now }: { data: PatientCareTimeline; now: Date }) {
  const toast = useToast();
  const [copying, setCopying] = useState<string | null>(null);

  async function copyReminder(id: string, text: string) {
    setCopying(id);
    const ok = await copyText(text);
    toast.push(ok ? "success" : "error", ok ? "Đã sao chép nội dung." : "Không sao chép được.");
    setCopying(null);
  }

  const { control, autonomy, open_handoff: open } = data;
  const sla = open ? slaState(open.sla_due_at, now) : null;

  return (
    <div className="space-y-4">
      <SectionCard title="Trạng thái" subtitle="Ai đang phụ trách cuộc trò chuyện này">
        <dl className="grid gap-4 sm:grid-cols-2">
          <Labelled label="Người phụ trách">
            {control.state === "STAFF"
              ? (control.staff_owner_name ?? "Một nhân viên")
              : control.state === "AUTO"
                ? "Agent"
                : "Chưa có, đang hỏi người nhận"}
          </Labelled>
          <Labelled label="Từ lúc">{formatDateTime(control.since)}</Labelled>
          <Labelled label="Mức tự chủ hiện tại">{LEVEL_LABEL[autonomy.effective_level]}</Labelled>
          <Labelled label="Mức gốc của agent">{LEVEL_LABEL[autonomy.base_level]}</Labelled>
          {autonomy.override_level && (
            <Labelled label="Đang hạ tạm thời">
              {LEVEL_LABEL[autonomy.override_level]}
              {autonomy.override_until ? `, đến ${formatDateTime(autonomy.override_until)}` : ""}
            </Labelled>
          )}
          {autonomy.paused && (
            <Labelled label="Agent">
              <Badge tone="red">Đang tạm dừng</Badge>
            </Labelled>
          )}
          {control.release_note && (
            <Labelled label="Ghi chú lần trả lại gần nhất">{control.release_note}</Labelled>
          )}
        </dl>
      </SectionCard>

      {open && (
        <SectionCard title="Vì sao agent nhờ người" subtitle="Yêu cầu đang mở">
          <div className="flex flex-wrap items-center gap-1.5">
            <UrgencyBadge urgency={open.urgency} />
            <DepthBadge depth={open.depth} />
            {open.required_skill && (
              <Badge tone="gray">Cần: {skillLabel(open.required_skill)}</Badge>
            )}
          </div>
          <p className="mt-3 text-[14px] font-medium text-ink">{reasonLabel(open.reason)}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">{open.summary}</p>
          <p className="mt-3 text-[12px] text-ink-soft">
            Mở lúc {formatDateTime(open.opened_at)} · Đang hỏi{" "}
            {open.current_candidate_name ?? "số trực 24/24"}
            {sla ? ` · ${sla.text}` : ""} · Độ tin cậy {Math.round(open.confidence * 100)}%
          </p>
        </SectionCard>
      )}

      <SectionCard
        title="Nháp đang chờ người duyệt"
        subtitle="Agent không gửi những tin này khi chưa có người duyệt"
      >
        {data.pending_drafts.length === 0 ? (
          <p className="text-[13px] text-ink-soft">Không có nháp nào đang chờ.</p>
        ) : (
          <ul className="space-y-2">
            {data.pending_drafts.map((draft) => (
              <li key={draft.review_item_id}>
                <Link
                  href={`/review?i=${draft.review_item_id}`}
                  className="flex min-h-11 flex-wrap items-center justify-between gap-2 rounded-lg border border-line px-3 py-2 hover:bg-tile/50"
                >
                  <span className="text-[14px] text-ink">{REVIEW_KIND_SHORT[draft.kind]}</span>
                  <span className="flex items-center gap-2 text-[12px] text-ink-soft">
                    {draft.requires_doctor && <Badge tone="red">Cần bác sĩ</Badge>}
                    {formatDateTime(draft.created_at)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Nhắc đang tạm dừng"
        subtitle="Khi nhân viên giữ cuộc trò chuyện, agent không gửi nhắc theo lịch; khi trả lại, agent rà soát lại"
      >
        {data.paused_reminders.length === 0 ? (
          <p className="text-[13px] text-ink-soft">Không có nhắc nào bị tạm dừng.</p>
        ) : (
          <ul className="space-y-3">
            {data.paused_reminders.map((reminder) => (
              <li key={reminder.id} className="gc-tile">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Badge tone="amber">Đã tạm dừng</Badge>
                  <span className="text-[12px] text-ink-soft">
                    Đến hạn {formatDateTime(reminder.due_at)}
                  </span>
                </div>
                {reminder.prepared_text && (
                  <>
                    <p className="mt-2 text-[13px] leading-relaxed text-ink">
                      {reminder.prepared_text}
                    </p>
                    <div className="mt-2">
                      <SecondaryButton
                        disabled={copying === reminder.id}
                        onClick={() => void copyReminder(reminder.id, reminder.prepared_text ?? "")}
                      >
                        Sao chép để gửi tay
                      </SecondaryButton>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Agent đã làm gì" subtitle="Mới nhất ở trên">
        {data.entries.length === 0 ? (
          <p className="text-[13px] text-ink-soft">Chưa có hoạt động nào.</p>
        ) : (
          <ol className="space-y-3">
            {data.entries.map((entry) => (
              <li key={entry.id} className="flex gap-3">
                <span className="w-24 shrink-0 pt-0.5 text-[12px] text-ink-soft">
                  {formatDateTime(entry.at)}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={ENTRY_TONE[entry.kind]}>{ENTRY_KIND_LABEL[entry.kind]}</Badge>
                    {entry.depth && <DepthBadge depth={entry.depth} />}
                  </div>
                  <p className="mt-1 text-[14px] text-ink">{codeLabel(entry.code)}</p>
                  {(entry.actor_name || entry.detail) && (
                    <p className="text-[12px] text-ink-soft">
                      {[entry.actor_name, entry.detail].filter(Boolean).join(" · ")}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </SectionCard>

      <SectionCard
        title="Agent nhớ gì về khách"
        subtitle="Chỉ là thói quen và dặn dò, không có hồ sơ y khoa"
      >
        {data.memory.length === 0 ? (
          <p className="text-[13px] text-ink-soft">Chưa có ghi nhớ nào.</p>
        ) : (
          <ul className="space-y-2">
            {data.memory.map((fact) => (
              <li key={fact.id} className="flex flex-wrap items-start justify-between gap-2">
                <span className="min-w-0 flex-1 text-[14px] text-ink">{fact.fact}</span>
                <Badge tone="gray" dot={false}>
                  {MEMORY_SOURCE_LABEL[fact.source]}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}
