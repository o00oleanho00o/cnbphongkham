"use client";

// One appointment on the board (old `.booking` card): time range, patient, note, doctor and the status chip,
// plus the one button that moves the visit forward. Everything else (confirm, miss, cancel, reschedule) is in
// the sheet that opens from the name. Status words are the old labels; colour only supports them.
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { cx } from "@/ui/classnames";
import { APPOINTMENT_STATUS_LABEL } from "@/lib/ops/labels";
import {
  ACTION_LABEL,
  STATUS_TONE,
  isActive,
  timeRange,
  type ScheduleAction,
  type ScheduleItem,
} from "@/lib/ops/schedule-view";

export function AppointmentCard({
  item,
  showDoctor,
  quick,
  busy,
  onOpen,
  onQuick,
}: {
  item: ScheduleItem;
  /** The doctor column already names the doctor; the week and phone lists show it on the card. */
  showDoctor: boolean;
  quick: ScheduleAction | null;
  busy: boolean;
  onOpen: (item: ScheduleItem) => void;
  onQuick: (item: ScheduleItem, action: ScheduleAction) => void;
}) {
  const name = item.patient_name ?? item.patient_code;
  return (
    <article
      className={cx(
        "min-w-0 rounded-tile border border-line bg-surface p-3 shadow-card",
        !isActive(item.status) && "opacity-75",
      )}
      aria-label={`${timeRange(item.starts_at, item.duration_min)} ${name}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-label font-semibold text-ink-soft tabular-nums">
          {timeRange(item.starts_at, item.duration_min)}
        </span>
        <Badge tone={STATUS_TONE[item.status]}>{APPOINTMENT_STATUS_LABEL[item.status]}</Badge>
      </div>
      <button
        type="button"
        onClick={() => onOpen(item)}
        className="mt-1.5 block max-w-full truncate text-left text-body-lg font-bold text-heading hover:underline"
        title="Mở chi tiết lịch hẹn"
      >
        {name}
      </button>
      <p className="truncate text-label text-ink-soft">
        {item.patient_name !== null && item.patient_name !== undefined
          ? `${item.patient_code} · `
          : ""}
        {item.note ?? "Không ghi chú"}
      </p>
      {showDoctor && (
        <p className="truncate text-label text-ink-soft">{item.doctor_name ?? "Chưa gán bác sĩ"}</p>
      )}
      {item.cancel_reason !== null && item.cancel_reason !== undefined && (
        <p className="mt-1 text-label text-danger">Lý do hủy: {item.cancel_reason}</p>
      )}
      {quick !== null && (
        <div className="mt-2">
          <Button
            variant="secondary"
            className="min-h-9 w-full sm:w-auto"
            disabled={busy}
            onClick={() => onQuick(item, quick)}
          >
            {ACTION_LABEL[quick]}
          </Button>
        </div>
      )}
    </article>
  );
}
