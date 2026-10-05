// Pure helpers of the reception table on "/today" (old "Hôm nay tại Pema", prototype/shared/crm-ui.js `today`):
// the status words and tiles, the three filters, the 25-row pages and the one set of buttons each row offers.
// The BE owns every rule (who may check in, which status may follow which); this file only decides what to OFFER.
import type { Schemas } from "@/lib/api";
import type { Permission } from "@/lib/session/session-context";
import type { ScheduleItem, StatusTone } from "@/lib/ops/schedule-view";

type Status = Schemas["AppointmentStatus"];

export const RECEPTION_PAGE_SIZE = 25;

/** Words of the old reception table (`statuses` in crm-ui.js); the schedule board keeps its own words. */
export const RECEPTION_STATUS_LABEL: Record<Status, string> = {
  booked: "Chưa đến",
  confirmed: "Đã xác nhận",
  arrived: "Đang chờ",
  in_progress: "Đang khám/điều trị",
  completed: "Hoàn tất",
  cancelled: "Đã hủy",
  missed: "Vắng hẹn",
};

export const RECEPTION_STATUS_TONE: Record<Status, StatusTone> = {
  booked: "info",
  confirmed: "info",
  arrived: "warning",
  in_progress: "brand",
  completed: "success",
  cancelled: "neutral",
  missed: "danger",
};

/** `pending` is the "Chưa đến" tile: the old tile counted booked and confirmed visits together. */
export type ReceptionStatusFilter = Status | "all" | "pending";

export const PENDING_LABEL = "Chưa đến (gồm đã xác nhận)";

export const RECEPTION_TILES: readonly { key: ReceptionStatusFilter; label: string }[] = [
  { key: "pending", label: "Chưa đến" },
  { key: "arrived", label: "Đang chờ" },
  { key: "in_progress", label: "Đang khám/điều trị" },
  { key: "completed", label: "Hoàn tất" },
  { key: "cancelled", label: "Đã hủy" },
  { key: "missed", label: "Vắng hẹn" },
];

export function matchesStatus(status: Status, filter: ReceptionStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "pending") return status === "booked" || status === "confirmed";
  return status === filter;
}

export type ReceptionCounts = {
  total: number;
  came: number;
  byTile: Record<ReceptionStatusFilter, number>;
};

export function receptionCounts(items: readonly ScheduleItem[]): ReceptionCounts {
  const count = (filter: ReceptionStatusFilter) =>
    items.filter((it) => matchesStatus(it.status, filter)).length;
  return {
    total: items.length,
    came: items.filter((it) => ["arrived", "in_progress", "completed"].includes(it.status)).length,
    byTile: {
      all: items.length,
      pending: count("pending"),
      booked: count("booked"),
      confirmed: count("confirmed"),
      arrived: count("arrived"),
      in_progress: count("in_progress"),
      completed: count("completed"),
      cancelled: count("cancelled"),
      missed: count("missed"),
    },
  };
}

export type ReceptionFilters = {
  status: ReceptionStatusFilter;
  /** "" = every doctor */
  doctorId: string;
  query: string;
};

/** Rows that pass the three filters, oldest start first (the old table sorted by clock time). */
export function filterReception(
  items: readonly ScheduleItem[],
  filters: ReceptionFilters,
  phoneOf: (item: ScheduleItem) => string,
): ScheduleItem[] {
  const needle = filters.query.trim().toLowerCase();
  return items
    .filter((it) => matchesStatus(it.status, filters.status))
    .filter((it) => filters.doctorId === "" || it.doctor_id === filters.doctorId)
    .filter(
      (it) =>
        needle === "" ||
        [it.patient_code, it.patient_name ?? "", phoneOf(it)]
          .join(" ")
          .toLowerCase()
          .includes(needle),
    )
    .toSorted((a, b) => a.starts_at.localeCompare(b.starts_at));
}

export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / RECEPTION_PAGE_SIZE));
}

export function pageOf<T>(rows: readonly T[], page: number): T[] {
  const safe = Math.min(Math.max(1, page), pageCount(rows.length));
  return rows.slice((safe - 1) * RECEPTION_PAGE_SIZE, safe * RECEPTION_PAGE_SIZE);
}

export type ReceptionAction = "check-in" | "miss" | "start";

export const RECEPTION_ACTION_LABEL: Record<ReceptionAction, string> = {
  "check-in": "Check-in",
  miss: "Vắng",
  start: "Mời vào phòng",
};

/**
 * `crm-ui.js`: booked or confirmed shows Check-in + Vắng, arrived shows "Mời vào phòng", every other status
 * shows "Mở 360" (the caller draws that link). The BE checks `appointment.check_in`; without it nothing is offered.
 */
export function receptionActions(
  status: Status,
  can: (permission: Permission) => boolean,
): ReceptionAction[] {
  if (!can("appointment.check_in")) return [];
  if (status === "booked" || status === "confirmed") return ["check-in", "miss"];
  if (status === "arrived") return ["start"];
  return [];
}

/** "32 tuổi" from the birth date, or "" when unknown. `today` is a `YYYY-MM-DD` in clinic time. */
export function ageLabel(birthDate: string | null | undefined, today: string): string {
  if (!birthDate) return "";
  const born = new Date(`${birthDate}T12:00:00Z`);
  const now = new Date(`${today}T12:00:00Z`);
  if (Number.isNaN(born.getTime()) || Number.isNaN(now.getTime())) return "";
  const beforeBirthday =
    now.getUTCMonth() < born.getUTCMonth() ||
    (now.getUTCMonth() === born.getUTCMonth() && now.getUTCDate() < born.getUTCDate());
  const age = now.getUTCFullYear() - born.getUTCFullYear() - (beforeBirthday ? 1 : 0);
  return age >= 0 ? `${age} tuổi` : "";
}
