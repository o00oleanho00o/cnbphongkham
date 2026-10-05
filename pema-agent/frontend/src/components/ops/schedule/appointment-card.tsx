"use client";

// One appointment on the board (old `.booking` card): time range, patient, note, doctor and the status chip,
// plus the one button that moves the visit forward. Everything else (confirm, miss, cancel, reschedule) is in
// the sheet that opens from the name. Status words are the old labels; colour only supports them.
// `compact` is the cell of the room grid: the card sits on a time axis, so it has a fixed height. A half hour
// shows time and name on one line (the status is the left edge colour and part of the accessible name); longer
// visits add the status chip and the next-step button.
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
  type StatusTone,
} from "@/lib/ops/schedule-view";

const EDGE_CLASS: Record<StatusTone, string> = {
  neutral: "border-l-ink-soft",
  info: "border-l-info",
  warning: "border-l-warning",
  brand: "border-l-brand-500",
  success: "border-l-success",
  danger: "border-l-danger",
};

export function AppointmentCard({
  item,
  showDoctor,
  showRoom = true,
  compact = false,
  quick,
  busy,
  onOpen,
  onQuick,
}: {
  item: ScheduleItem;
  /** The doctor column already names the doctor; the week and phone lists show it on the card. */
  showDoctor: boolean;
  /** The room column of the room grid already names the room; the doctor board and the lists show it. */
  showRoom?: boolean;
  /** A cell of the room grid: fixed height, no note line. */
  compact?: boolean;
  quick: ScheduleAction | null;
  busy: boolean;
  onOpen: (item: ScheduleItem) => void;
  onQuick: (item: ScheduleItem, action: ScheduleAction) => void;
}) {
  const name = item.patient_name ?? item.patient_code;
  const range = timeRange(item.starts_at, item.duration_min);
  const statusText = APPOINTMENT_STATUS_LABEL[item.status];
  const where = [
    showDoctor ? (item.doctor_name ?? "Chưa gán bác sĩ") : "",
    showRoom ? (item.room_name ?? "") : "",
  ]
    .filter((part) => part !== "")
    .join(" · ");

  if (compact) {
    const roomy = item.duration_min >= 45;
    return (
      <article
        className={cx(
          "h-full min-w-0 overflow-hidden rounded-tile border border-l-4 border-line bg-surface px-1.5 py-1 shadow-card",
          EDGE_CLASS[STATUS_TONE[item.status]],
          !isActive(item.status) && "opacity-75",
        )}
        aria-label={`${range} ${name} ${statusText}`}
      >
        <button
          type="button"
          onClick={() => onOpen(item)}
          className="block w-full truncate text-left text-label leading-tight font-bold text-heading hover:underline"
          title={`${range} · ${name} · ${statusText}. Mở chi tiết lịch hẹn`}
        >
          <span className="font-semibold text-ink-soft tabular-nums">{range.slice(0, 5)}</span>{" "}
          {name}
        </button>
        {roomy && (
          <div className="mt-0.5 flex items-center gap-1.5">
            <Badge tone={STATUS_TONE[item.status]}>{statusText}</Badge>
            {quick !== null && (
              <button
                type="button"
                disabled={busy}
                onClick={() => onQuick(item, quick)}
                className="truncate text-label font-semibold text-link hover:underline disabled:opacity-60"
              >
                {ACTION_LABEL[quick]}
              </button>
            )}
          </div>
        )}
      </article>
    );
  }

  return (
    <article
      className={cx(
        "min-w-0 rounded-tile border border-line bg-surface p-3 shadow-card",
        !isActive(item.status) && "opacity-75",
      )}
      aria-label={`${range} ${name}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-label font-semibold text-ink-soft tabular-nums">{range}</span>
        <Badge tone={STATUS_TONE[item.status]}>{statusText}</Badge>
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
      {where !== "" && <p className="truncate text-label text-ink-soft">{where}</p>}
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
