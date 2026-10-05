"use client";

import Link from "next/link";
import { memo } from "react";

import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import { IconCopy } from "@/components/admin/shared/ops-icons";
import { PriorityBadge, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { channelOfTask, isManualSend } from "@/lib/ops/crm-task-view";
import { dueLabel, isOverdue } from "@/lib/ops/format";
import { CHANNEL_LABEL, OUTCOME_LABEL, RULE_LABEL, TASK_STATUS_LABEL } from "@/lib/ops/labels";

type CrmTask = Schemas["CrmTaskOut"];

export type TaskCardProps = {
  task: CrmTask;
  patientName: string;
  marketingOptOut: boolean;
  /** `crm.task.resolve`: without it the card is read-only apart from copying */
  canResolve: boolean;
  onCopy: (task: CrmTask) => void;
  onMarkDone: (task: CrmTask) => void;
  onRecord: (task: CrmTask) => void;
};

function TaskCardView({
  task,
  patientName,
  marketingOptOut,
  canResolve,
  onCopy,
  onMarkDone,
  onRecord,
}: TaskCardProps) {
  const open = task.status === "open" || task.status === "rescheduled";
  const manual = isManualSend(task);
  const overdue = open && isOverdue(task.due_at);

  return (
    <article className="gc-card p-4" aria-label={`${patientName}, ${RULE_LABEL[task.rule_key]}`}>
      <div className="flex items-start gap-3">
        <InitialAvatar name={patientName} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <Link
              href={`/patients/${task.patient_id}`}
              className="text-[15px] font-semibold text-ink hover:text-brand-500"
            >
              {patientName}
            </Link>
            <span className="text-[12px] text-ink-soft">{task.patient_code}</span>
            {marketingOptOut && <Badge tone="amber">Từ chối tin quảng bá</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <Badge tone="blue" dot={false}>
              {RULE_LABEL[task.rule_key]}
            </Badge>
            <PriorityBadge priority={task.priority} />
            {manual && (
              <Badge tone="gray" dot={false}>
                Gửi tay · {CHANNEL_LABEL[channelOfTask(task)]}
              </Badge>
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div
            className={`text-[13px] font-semibold ${overdue ? "text-red-600 dark:text-red-400" : "text-ink"}`}
          >
            {dueLabel(task.due_at)}
          </div>
          {task.owner_name && <div className="text-[11px] text-ink-soft">{task.owner_name}</div>}
        </div>
      </div>

      <p className="mt-3 text-[13px] text-ink-soft">{task.reason}</p>

      <div className="mt-2 rounded-lg bg-tile/60 px-3 py-2.5">
        <div className="mb-0.5 text-[11px] font-semibold tracking-wide text-ink-soft uppercase">
          Nội dung gợi ý
        </div>
        <p className="text-[13px] leading-relaxed text-ink">{task.suggested_action}</p>
      </div>

      {open ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {manual && (
            <SecondaryButton onClick={() => onCopy(task)}>
              <IconCopy size={16} />
              Sao chép nội dung
            </SecondaryButton>
          )}
          {canResolve && manual && (
            <PrimaryButton onClick={() => onMarkDone(task)}>Đánh dấu đã làm</PrimaryButton>
          )}
          {canResolve && !manual && (
            <PrimaryButton onClick={() => onRecord(task)}>Ghi nhận kết quả</PrimaryButton>
          )}
          {canResolve && manual && (
            <SecondaryButton onClick={() => onRecord(task)}>Ghi nhận khác</SecondaryButton>
          )}
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
          <Badge tone="green">{TASK_STATUS_LABEL[task.status]}</Badge>
          {task.resolution && (
            <span className="text-ink-soft">
              {OUTCOME_LABEL[task.resolution as keyof typeof OUTCOME_LABEL] ?? task.resolution}
            </span>
          )}
        </div>
      )}
    </article>
  );
}

export const TaskCard = memo(TaskCardView);
