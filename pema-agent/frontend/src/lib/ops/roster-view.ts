// The week view and the form of the roster (package O, frames WM30-WM41): who covers which identity, when. Pure, so
// the calendar maths and the sentences are tested without a screen. The BE decides who may edit (owner, manager),
// whether a person can hold threads, and what an overlap means; this only lays the entries out and checks what
// the form can see is wrong. All dates are clinic dates ("YYYY-MM-DD"), worked in UTC so the zone of the browser
// never moves a day.
import type { Schemas } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/session/session-context";

type Entry = Schemas["RosterEntryOut"];
type Weekday = Schemas["Weekday"];
type Role = Schemas["Role"];

export const WEEKDAYS: readonly Weekday[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const SHORT: Record<Weekday, string> = {
  mon: "T2",
  tue: "T3",
  wed: "T4",
  thu: "T5",
  fri: "T6",
  sat: "T7",
  sun: "CN",
};
export const WEEKDAY_CHIP: Record<Weekday, string> = {
  mon: "Thứ 2",
  tue: "Thứ 3",
  wed: "Thứ 4",
  thu: "Thứ 5",
  fri: "Thứ 6",
  sat: "Thứ 7",
  sun: "CN",
};
const LONG_DAY: Record<Weekday, string> = {
  mon: "Thứ hai",
  tue: "Thứ ba",
  wed: "Thứ tư",
  thu: "Thứ năm",
  fri: "Thứ sáu",
  sat: "Thứ bảy",
  sun: "Chủ nhật",
};

const DAY_MS = 86_400_000;
const NOTE_MAX = 200;

function parse(dateKey: string): number {
  return Date.parse(`${dateKey}T00:00:00Z`);
}

export function addDays(dateKey: string, days: number): string {
  return new Date(parse(dateKey) + days * DAY_MS).toISOString().slice(0, 10);
}

export function weekdayOf(dateKey: string): Weekday {
  const index = (new Date(parse(dateKey)).getUTCDay() + 6) % 7;
  return WEEKDAYS[index] ?? "mon";
}

/** The Monday of the week that holds `dateKey`. */
export function mondayOf(dateKey: string): string {
  return addDays(dateKey, -WEEKDAYS.indexOf(weekdayOf(dateKey)));
}

export function weekDates(monday: string): string[] {
  return WEEKDAYS.map((_, i) => addDays(monday, i));
}

const dayMonth = (dateKey: string): string => `${dateKey.slice(8, 10)}/${dateKey.slice(5, 7)}`;

/** "T2, 14/09". */
export function dayTitle(dateKey: string): string {
  return `${SHORT[weekdayOf(dateKey)]}, ${dayMonth(dateKey)}`;
}

/** "Tuần 14/09 – 20/09/2026". */
export function weekTitle(monday: string): string {
  return `Tuần ${dayMonth(monday)} – ${dayMonth(addDays(monday, 6))}/${addDays(monday, 6).slice(0, 4)}`;
}

/** "Chủ nhật 20/09/2026 · 09:00", the subtitle of the on-duty card. */
export function momentTitle(dateKey: string, hhmm: string): string {
  return `${LONG_DAY[weekdayOf(dateKey)]} ${dayMonth(dateKey)}/${dateKey.slice(0, 4)} · ${hhmm}`;
}

export function entriesOn(entries: readonly Entry[], dateKey: string): Entry[] {
  const weekday = weekdayOf(dateKey);
  return entries
    .filter((e) =>
      e.on_date === null ? (e.weekdays ?? []).includes(weekday) : e.on_date === dateKey,
    )
    .toSorted((a, b) => a.start.localeCompare(b.start) || a.user_name.localeCompare(b.user_name));
}

export function countText(count: number): string {
  return `${count} ca`;
}

export type RoleGroup = "cs" | "doctor" | "manager";

export function roleGroup(role: Role): RoleGroup {
  if (role === "doctor") return "doctor";
  if (role === "owner" || role === "manager") return "manager";
  return "cs";
}

export const ROLE_GROUP_LABEL: Record<RoleGroup, string> = {
  cs: "CSKH",
  doctor: "Bác sĩ",
  manager: "Chủ phòng khám, quản lý",
};

/** "CSKH · ca 08:00–12:00" under a person on duty. */
export function onDutyLine(role: Role, entry: Pick<Entry, "start" | "end"> | null): string {
  const label = ROLE_LABEL[role];
  return entry ? `${label} · ca ${entry.start}–${entry.end}` : label;
}

export function shiftRange(entry: Pick<Entry, "start" | "end">): string {
  return `${entry.start}–${entry.end}`;
}

export type RosterMode = "weekly" | "date";

export type RosterForm = {
  accountId: string;
  userId: string;
  mode: RosterMode;
  weekdays: Weekday[];
  date: string;
  start: string;
  end: string;
  note: string;
};

export function emptyForm(
  accountId: string,
  userId: string,
  weekday: Weekday | null = null,
): RosterForm {
  return {
    accountId,
    userId,
    mode: "weekly",
    weekdays: weekday ? [weekday] : ["mon", "tue", "wed", "thu", "fri"],
    date: "",
    start: "08:00",
    end: "12:00",
    note: "",
  };
}

export function formOfEntry(entry: Entry): RosterForm {
  return {
    accountId: entry.account_id,
    userId: entry.user_id,
    mode: entry.on_date === null ? "weekly" : "date",
    weekdays: entry.weekdays ?? [],
    date: entry.on_date ?? "",
    start: entry.start,
    end: entry.end,
    note: entry.note ?? "",
  };
}

export function toggleWeekday(current: readonly Weekday[], day: Weekday): Weekday[] {
  const next = current.includes(day) ? current.filter((d) => d !== day) : [...current, day];
  return WEEKDAYS.filter((d) => next.includes(d));
}

export type RosterErrors = Partial<Record<"user" | "weekdays" | "date" | "time" | "note", string>>;

export function validateRoster(form: RosterForm): RosterErrors {
  const weeklyWithoutDay = form.mode === "weekly" && form.weekdays.length === 0;
  const dateWithoutDay = form.mode === "date" && form.date === "";
  return {
    ...(form.userId === "" ? { user: "Chọn người trực." } : {}),
    ...(weeklyWithoutDay ? { weekdays: "Chọn ít nhất một thứ." } : {}),
    ...(dateWithoutDay ? { date: "Chọn ngày." } : {}),
    ...(form.start === form.end ? { time: "Giờ bắt đầu và giờ kết thúc phải khác nhau." } : {}),
    ...(form.note.length > NOTE_MAX ? { note: "Ghi chú tối đa 200 ký tự." } : {}),
  };
}

/** True when the shift ends the next morning (the end is before the start). */
export function isOvernight(form: Pick<RosterForm, "start" | "end">): boolean {
  return form.end < form.start;
}

/** The line under the time boxes; null while the shift ends the same day. */
export function overnightText(form: RosterForm): string | null {
  if (!isOvernight(form)) return null;
  return form.mode === "date"
    ? `Ca kết thúc vào ${form.end} sáng hôm sau.`
    : "Giờ đến nhỏ hơn giờ từ: ca kết thúc vào sáng hôm sau.";
}

export function createBody(form: RosterForm): Schemas["RosterEntryCreate"] {
  return {
    account_id: form.accountId,
    user_id: form.userId,
    start: form.start,
    end: form.end,
    note: form.note.trim() || null,
    weekdays: form.mode === "weekly" ? form.weekdays : null,
    on_date: form.mode === "date" ? form.date : null,
  };
}

export function updateBody(form: RosterForm, version: number): Schemas["RosterEntryUpdate"] {
  return {
    user_id: form.userId,
    start: form.start,
    end: form.end,
    note: form.note.trim() || null,
    weekdays: form.mode === "weekly" ? form.weekdays : null,
    on_date: form.mode === "date" ? form.date : null,
    version,
  };
}

/** "Đã kết thúc ca: 4 hội thoại chuyển người trực, 1 về hàng chờ, 0 bỏ qua." */
export function endShiftText(result: Schemas["EndShiftResult"]): string {
  return `Đã kết thúc ca: ${result.rerouted} hội thoại chuyển người trực, ${result.to_queue} về hàng chờ, ${result.skipped} bỏ qua.`;
}
