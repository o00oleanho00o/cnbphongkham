"use client";

// One round that is waiting for a person: who, why the agent asked, the PII-masked summary it wrote, where the
// person stands in the chain and how long is left. "Nhận" and "Từ chối" are shown when the backend says the caller
// may (`can_accept`, `can_decline`); the screen decides nothing about who may.
import Link from "next/link";

import { IconClock } from "@/components/admin/shared/dashboard-icons";
import { Badge } from "@/components/admin/shared/ui-bits";
import { DepthBadge, UrgencyBadge } from "@/components/care/care-ui";
import { PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import type { HandoffWaiting } from "@/lib/care/care-types";
import { reasonLabel, skillLabel } from "@/lib/care/labels";
import { ageText, slaState } from "@/lib/care/sla";

export function HandoffCard({
  item,
  now,
  busy,
  error,
  onAccept,
  onDecline,
}: {
  item: HandoffWaiting;
  now: Date;
  busy: boolean;
  error: string;
  onAccept: (item: HandoffWaiting) => void;
  onDecline: (item: HandoffWaiting) => void;
}) {
  const sla = slaState(item.sla_due_at, now);
  return (
    <article
      aria-label={`Yêu cầu của ${item.patient_name}`}
      className={`gc-card p-4 sm:p-5 ${item.urgency === "urgent" ? "border-red-300 dark:border-red-900/60" : ""}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <Link
            href={`/care/patients/${item.patient_id}/timeline`}
            className="text-[16px] font-semibold text-ink hover:text-brand-500"
          >
            {item.patient_name}
          </Link>
          <p className="mt-0.5 text-[12px] text-ink-soft">
            Mở {ageText(item.opened_at, now)} · bước {item.position}/{item.chain_length} trong chuỗi
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <UrgencyBadge urgency={item.urgency} />
          <DepthBadge depth={item.depth} />
        </div>
      </div>

      <p className="mt-3 text-[14px] font-medium text-ink">{reasonLabel(item.reason)}</p>
      <p className="mt-1 text-[13px] leading-relaxed text-ink-soft">{item.summary}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px] text-ink-soft">
        {item.required_skill && <Badge tone="gray">Cần: {skillLabel(item.required_skill)}</Badge>}
        <span>Độ tin cậy của agent {Math.round(item.confidence * 100)}%</span>
        {item.on_call_step && <Badge tone="amber">Đã tới số trực 24/24</Badge>}
        {item.suggested_by_name && <span>{item.suggested_by_name} gợi ý bạn nhận</span>}
        {sla && (
          <span
            className={`inline-flex items-center gap-1 font-medium ${
              sla.overdue
                ? "text-red-700 dark:text-red-300"
                : sla.soon
                  ? "text-amber-700 dark:text-amber-300"
                  : ""
            }`}
          >
            <IconClock size={14} />
            {sla.text}
          </span>
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 text-[13px] text-red-700 dark:text-red-300">
          {error}
        </p>
      )}

      {(item.can_accept || item.can_decline) && (
        <div className="mt-4 flex flex-col gap-2 sm:flex-row">
          {item.can_accept && (
            <PrimaryButton disabled={busy} onClick={() => onAccept(item)}>
              Nhận cuộc trò chuyện
            </PrimaryButton>
          )}
          {item.can_decline && (
            <SecondaryButton disabled={busy} onClick={() => onDecline(item)}>
              Từ chối
            </SecondaryButton>
          )}
        </div>
      )}
    </article>
  );
}
