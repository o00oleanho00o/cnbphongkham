// Input checks of the care screens. They only save a round trip for an obvious slip (an empty reason, a number
// that is not a number); the backend validates again and its refusal is shown as it comes, so none of this is a
// rule of the clinic. The limits mirror the contract (`pema_contracts/care.py`) and are not decisions.
import type {
  CareLevel,
  DepthSignal,
  CareMatrix,
  Shift,
  ShiftInterval,
  Weekday,
} from "@/lib/care/care-types";

export const REASON_MAX = 500;
export const NOTE_MAX = 500;
export const INSTRUCTION_MAX = 500;

export function declineError(reason: string): string {
  const text = reason.trim();
  if (text === "") return "Hãy ghi lý do từ chối.";
  if (text.length > REASON_MAX) return `Lý do tối đa ${REASON_MAX} ký tự.`;
  return "";
}

export function instructionError(text: string): string {
  const value = text.trim();
  if (value === "") return "Hãy nhập nội dung cần nói với agent.";
  if (value.length > INSTRUCTION_MAX) return `Nội dung tối đa ${INSTRUCTION_MAX} ký tự.`;
  return "";
}

export type ReleaseDraft = { note: string; level: CareLevel | ""; days: string };

/** The `days` of a draft as a whole number, or null when it is empty or not a whole number. */
export function parseDays(raw: string): number | null {
  const text = raw.trim();
  if (!/^\d{1,3}$/.test(text)) return null;
  return Number.parseInt(text, 10);
}

export function releaseError(draft: ReleaseDraft, maxDays: number): string {
  if (draft.note.length > NOTE_MAX) return `Ghi chú tối đa ${NOTE_MAX} ký tự.`;
  if (draft.level === "") return "";
  const days = parseDays(draft.days);
  if (days === null) return "Hãy nhập số ngày áp dụng mức đã chọn.";
  if (days < 1 || days > maxDays) return `Số ngày từ 1 đến ${maxDays}.`;
  return "";
}

/** The body of the release call from the form: no level means "keep the agent's own level". */
export function releaseBody(draft: ReleaseDraft): {
  note: string;
  level: CareLevel | null;
  days: number | null;
} {
  const note = draft.note.trim();
  if (draft.level === "") return { note, level: null, days: null };
  return { note, level: draft.level, days: parseDays(draft.days) };
}

const ON_CALL_NUMBER = /^\+?\d{8,15}$/;

export function onCallErrors(draft: { zalo_number: string; owner: string }): {
  number: string;
  owner: string;
} {
  return {
    number: ON_CALL_NUMBER.test(draft.zalo_number.trim())
      ? ""
      : "Số gồm 8 đến 15 chữ số, có thể bắt đầu bằng +.",
    owner: draft.owner.trim() === "" ? "Hãy ghi người phụ trách số trực." : "",
  };
}

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

export function intervalError(interval: ShiftInterval): string {
  if (!HHMM.test(interval.start) || !HHMM.test(interval.end)) return "Giờ theo dạng 08:00.";
  if (interval.start === interval.end) return "Giờ bắt đầu và kết thúc không được trùng nhau.";
  return "";
}

export function shiftError(shift: Shift): string {
  const errors = Object.values(shift)
    .flat()
    .map(intervalError)
    .filter((message) => message !== "");
  return errors[0] ?? "";
}

export function addInterval(shift: Shift, day: Weekday): Shift {
  return { ...shift, [day]: [...shift[day], { start: "08:00", end: "17:00" }] };
}

export function removeInterval(shift: Shift, day: Weekday, index: number): Shift {
  return { ...shift, [day]: shift[day].filter((_, i) => i !== index) };
}

export function changeInterval(
  shift: Shift,
  day: Weekday,
  index: number,
  patch: Partial<ShiftInterval>,
): Shift {
  return {
    ...shift,
    [day]: shift[day].map((interval, i) => (i === index ? { ...interval, ...patch } : interval)),
  };
}

/** Skills as typed in the editor ("dat_lich, laser") to the list the API takes. */
export function parseSkills(raw: string): string[] {
  const seen = new Set<string>();
  raw
    .split(/[\s,;]+/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s !== "")
    .forEach((s) => seen.add(s));
  return [...seen];
}

export function setDepthRow(
  matrix: CareMatrix["handoff"],
  signal: DepthSignal,
  fromDepth: CareMatrix["handoff"]["rows"][number]["from_depth"],
): CareMatrix["handoff"] {
  return {
    ...matrix,
    rows: matrix.rows.map((row) =>
      row.signal === signal ? { ...row, from_depth: fromDepth } : row,
    ),
  };
}

export function setAutonomyRule(
  autonomy: CareMatrix["autonomy"],
  actionType: string,
  patch: Partial<CareMatrix["autonomy"]["rules"][number]>,
): CareMatrix["autonomy"] {
  return {
    ...autonomy,
    rules: autonomy.rules.map((rule) =>
      rule.action_type === actionType && !rule.hard_human ? { ...rule, ...patch } : rule,
    ),
  };
}

/** A number typed in a field to a bounded number; null for anything that is not one. */
export function parseBounded(raw: string, min: number, max: number): number | null {
  const text = raw.trim().replace(",", ".");
  if (text === "" || !/^-?\d*\.?\d+$/.test(text)) return null;
  const value = Number(text);
  return value >= min && value <= max ? value : null;
}

export function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
