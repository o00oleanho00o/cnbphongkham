// Date helpers of the clinic screens. The clinic works in Vietnam time (+07:00) whatever the zone of the
// browser, same reasoning as `format-bot-time.ts` of the ported dashboard: "due at 9am" is 9am at the
// clinic, not for whoever happens to look from another zone. Every API boundary is ISO 8601 with offset.
export const CLINIC_TIME_ZONE = "Asia/Ho_Chi_Minh";

const DAY_MS = 86_400_000;

type DateParts = { year: string; month: string; day: string };

function partsInClinicZone(date: Date): DateParts {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: CLINIC_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "00";
  return { year: get("year"), month: get("month"), day: get("day") };
}

/** `YYYY-MM-DD` of the clinic's today. */
export function clinicDateKey(date: Date = new Date()): string {
  const { year, month, day } = partsInClinicZone(date);
  return `${year}-${month}-${day}`;
}

/** Last second of the clinic's today, the `due_by` of "Việc hôm nay". */
export function endOfTodayIso(date: Date = new Date()): string {
  return `${clinicDateKey(date)}T23:59:59+07:00`;
}

/** "20/09 09:00" in clinic time. Built from parts: the vi-VN pattern of Intl prints "09:00 20-09". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "-";
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: CLINIC_TIME_ZONE,
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  // some engines print midnight as "24"
  const hour = get("hour") === "24" ? "00" : get("hour");
  return `${get("day")}/${get("month")} ${hour}:${get("minute")}`;
}

/** "20/09/2026" from an ISO date or datetime. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value.length === 10 ? `${value}T00:00:00+07:00` : value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: CLINIC_TIME_ZONE,
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

function dayNumber(dateKey: string): number {
  return Math.floor(Date.parse(`${dateKey}T00:00:00Z`) / DAY_MS);
}

/** Whole clinic-calendar days from `from` to `to` (negative when `to` is earlier). */
export function daysBetween(from: Date, to: Date): number {
  return dayNumber(clinicDateKey(to)) - dayNumber(clinicDateKey(from));
}

function timeOfDay(iso: string): string {
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: CLINIC_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(iso));
}

/** "Hôm nay 09:00", "Ngày mai 14:30", "Quá hạn 2 ngày", "20/09 09:00". */
export function dueLabel(dueIso: string, now: Date = new Date()): string {
  const due = new Date(dueIso);
  if (Number.isNaN(due.getTime())) return "-";
  const diff = daysBetween(now, due);
  if (diff === 0) return `Hôm nay ${timeOfDay(dueIso)}`;
  if (diff === 1) return `Ngày mai ${timeOfDay(dueIso)}`;
  if (diff < 0) return `Quá hạn ${-diff} ngày`;
  return formatDateTime(dueIso);
}

/** Overdue means an earlier clinic day than today; a task due earlier today is just due. */
export function isOverdue(dueIso: string, now: Date = new Date()): boolean {
  const due = new Date(dueIso);
  if (Number.isNaN(due.getTime())) return false;
  return daysBetween(now, due) < 0;
}

export function ageYears(
  birthDate: string | null | undefined,
  now: Date = new Date(),
): number | null {
  if (!birthDate) return null;
  const birth = new Date(`${birthDate}T00:00:00Z`);
  if (Number.isNaN(birth.getTime())) return null;
  const today = new Date(`${clinicDateKey(now)}T00:00:00Z`);
  const years = today.getUTCFullYear() - birth.getUTCFullYear();
  const hadBirthday =
    today.getUTCMonth() > birth.getUTCMonth() ||
    (today.getUTCMonth() === birth.getUTCMonth() && today.getUTCDate() >= birth.getUTCDate());
  return hadBirthday ? years : years - 1;
}

/** `datetime-local` value ("2026-09-21T09:00", clinic time) to the ISO string with offset the API needs. */
export function localInputToIso(value: string): string {
  return `${value}:00+07:00`;
}
