// Pure helpers of the schedule screen ("Điều phối lịch"). Behaviour source: prototype/shared/operations-ui.js
// (`schedule`, `edit`, `handle`) and crm-automation.js (`reception`: which status may follow which). The BE owns
// every rule (hours, double booking, who may do what); this file only decides which buttons to OFFER and how to
// group rows, so a click that the BE refuses still ends in the BE's own sentence.
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";

type Status = Schemas["AppointmentStatus"];
export type ScheduleItem = Schemas["ScheduleItem"];

export type ScheduleAction = "confirm" | "check-in" | "start" | "complete" | "miss" | "cancel";

export const ACTION_LABEL: Record<ScheduleAction, string> = {
  confirm: "Xác nhận lịch",
  "check-in": "Check-in",
  start: "Bắt đầu điều trị",
  complete: "Hoàn tất",
  miss: "Vắng hẹn",
  cancel: "Hủy lịch",
};

/** Toast after a transition, in the words of the old web where it had one. */
export const ACTION_DONE: Record<ScheduleAction, string> = {
  confirm: "Đã xác nhận lịch hẹn.",
  "check-in": "Đã check-in, bệnh nhân đang chờ.",
  start: "Đã bắt đầu điều trị.",
  complete: "Đã hoàn tất lịch hẹn.",
  miss: "Đã ghi nhận vắng hẹn.",
  cancel: "Đã hủy lịch, giữ lại lịch sử.",
};

/** The permission the BE asks for each transition (`confirm` and `cancel` edit the schedule). */
const ACTION_PERMISSION: Record<ScheduleAction, Permission> = {
  confirm: "appointment.write",
  cancel: "appointment.write",
  "check-in": "appointment.check_in",
  start: "appointment.check_in",
  complete: "appointment.check_in",
  miss: "appointment.check_in",
};

/** `crm-automation.js` `reception` plus `confirm` and `cancel` of `operations-data.js`. */
const NEXT: Record<Status, readonly ScheduleAction[]> = {
  booked: ["confirm", "check-in", "miss", "cancel"],
  confirmed: ["check-in", "miss", "cancel"],
  arrived: ["start", "cancel"],
  in_progress: ["complete"],
  completed: [],
  cancelled: [],
  missed: [],
};

export function allowedActions(
  status: Status,
  can: (permission: Permission) => boolean,
): ScheduleAction[] {
  return NEXT[status].filter((action) => can(ACTION_PERMISSION[action]));
}

/** The one button a card shows: the next step of the visit (cancel and the rest live in the sheet). */
export function quickAction(
  status: Status,
  can: (permission: Permission) => boolean,
): ScheduleAction | null {
  const order: ScheduleAction[] = ["check-in", "start", "complete"];
  return allowedActions(status, can).find((a) => order.includes(a)) ?? null;
}

/** A booked or confirmed visit may still be moved; anything later is history. */
export function isEditable(status: Status): boolean {
  return status === "booked" || status === "confirmed";
}

/** Cancelled and missed visits free their slot and are hidden from the board unless asked for. */
export function isActive(status: Status): boolean {
  return status !== "cancelled" && status !== "missed";
}

export type StatusTone = "neutral" | "info" | "warning" | "brand" | "success" | "danger";

export const STATUS_TONE: Record<Status, StatusTone> = {
  booked: "neutral",
  confirmed: "info",
  arrived: "warning",
  in_progress: "brand",
  completed: "success",
  cancelled: "danger",
  missed: "danger",
};

/** Order of the status chips and of the breakdown, the order of the visit. */
export const STATUS_ORDER: readonly Status[] = [
  "booked",
  "confirmed",
  "arrived",
  "in_progress",
  "completed",
  "missed",
  "cancelled",
];

// ---------------------------------------------------------------------------------------------- dates

const DAY_MS = 86_400_000;

/** `YYYY-MM-DD` plus `n` days (calendar arithmetic in UTC, so no zone or DST can move it). */
export function addDays(day: string, n: number): string {
  return new Date(Date.parse(`${day}T12:00:00Z`) + n * DAY_MS).toISOString().slice(0, 10);
}

export function isDayKey(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && addDays(value, 0) === value;
}

/** The API sends clinic time with the +07:00 offset, so the day and the clock are plain slices. */
export const dayOf = (iso: string): string => iso.slice(0, 10);
export const clockOf = (iso: string): string => iso.slice(11, 16);

/** "08:30–09:15". */
export function timeRange(startsAt: string, durationMin: number): string {
  const start = Number(startsAt.slice(11, 13)) * 60 + Number(startsAt.slice(14, 16));
  const end = start + durationMin;
  const clock = (m: number) =>
    `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
  return `${clock(start)}–${clock(end)}`;
}

const WEEKDAY = ["CN", "T2", "T3", "T4", "T5", "T6", "T7"] as const;

/** "T2 21/09". */
export function dayLabel(day: string): string {
  const weekday = WEEKDAY[new Date(`${day}T12:00:00Z`).getUTCDay()] ?? "";
  return `${weekday} ${day.slice(8, 10)}/${day.slice(5, 7)}`;
}

/** The `datetime` the API wants, from the two inputs of the form (clinic time). */
export function toStartsAt(day: string, clock: string): string {
  return `${day}T${clock}:00+07:00`;
}

// ---------------------------------------------------------------------------------------------- groups

export function groupByDay(items: readonly ScheduleItem[], fromDay: string, days: number) {
  return Array.from({ length: days }, (_, i) => {
    const day = addDays(fromDay, i);
    return { day, items: items.filter((it) => dayOf(it.starts_at) === day) };
  });
}

export type DoctorColumn = { id: string | null; name: string; items: ScheduleItem[] };

/** One column per doctor of the clinic (rooms are not modelled yet), plus one for appointments without a doctor. */
export function groupByDoctor(
  items: readonly ScheduleItem[],
  doctors: readonly Schemas["ScheduleDoctor"][],
): DoctorColumn[] {
  const columns: DoctorColumn[] = doctors.map((d) => ({
    id: d.id,
    name: d.name,
    items: items.filter((it) => it.doctor_id === d.id),
  }));
  const known = new Set(doctors.map((d) => d.id));
  const loose = items.filter((it) => it.doctor_id === null || !known.has(it.doctor_id));
  return loose.length > 0
    ? [...columns, { id: null, name: "Chưa gán bác sĩ", items: loose }]
    : columns;
}

export type DaySummary = {
  total: number;
  treatmentMin: number;
  waiting: number;
  closed: number;
  byStatus: Record<Status, number>;
};

/** Numbers of the four tiles above the board; `total` and `treatmentMin` count active visits only (JS `filtered`). */
export function summarize(items: readonly ScheduleItem[]): DaySummary {
  const byStatus = items.reduce<Record<Status, number>>(
    (counts, it) => ({ ...counts, [it.status]: counts[it.status] + 1 }),
    { booked: 0, confirmed: 0, arrived: 0, in_progress: 0, completed: 0, cancelled: 0, missed: 0 },
  );
  const active = items.filter((it) => isActive(it.status));
  return {
    total: active.length,
    treatmentMin: active.reduce((sum, it) => sum + it.duration_min, 0),
    waiting: byStatus.arrived,
    closed: byStatus.cancelled + byStatus.missed,
    byStatus,
  };
}
