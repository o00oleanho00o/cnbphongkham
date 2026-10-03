// Rules of the "Ghi buổi điều trị" form, ported from `save-session` of prototype/shared/clinic.js. The BE repeats
// every one of them (it is the authority); checking here only saves a round trip and puts the same sentence next
// to the field. Pure functions: the form component owns the state.
import { clinicDateKey } from "@/lib/ops/format";

export type SessionFormState = {
  planId: string;
  performedOn: string;
  sessionType: string;
  protocolId: string;
  nextVisitOn: string;
  note: string;
  aftercare: string;
  region: string;
  view: string;
  photoName: string;
  photoConsent: boolean;
};

export type PlanProgress = { completed: number; total: number };

/** After the session the CRM recalls the patient this many days later when the doctor gave no date. */
export const DEFAULT_NEXT_VISIT_DAYS = 30;

export const PLAN_FULL_MESSAGE =
  "Kế hoạch đã đủ buổi. Hãy điều chỉnh kế hoạch trước khi thêm buổi mới.";
export const NOTE_REQUIRED_MESSAGE = "Hãy ghi đánh giá trước buổi.";
export const AFTERCARE_REQUIRED_MESSAGE = "Hãy nhập hướng dẫn chăm sóc sau buổi.";
export const DATE_INVALID_MESSAGE = "Ngày buổi phải hợp lệ, từ buổi trước đến hôm nay.";
export const PHOTO_CONSENT_MESSAGE = "Cần xác nhận đồng ý ảnh khi lưu ảnh mốc.";

const DATE_SHAPE = /^\d{4}-\d{2}-\d{2}$/;

/** `YYYY-MM-DD` that is a real calendar day (the old check round-trips it through `Date`). */
export function isRealDate(value: string): boolean {
  if (!DATE_SHAPE.test(value)) return false;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function isPlanFull(plan: PlanProgress | null): boolean {
  return plan !== null && plan.completed >= plan.total;
}

/** Chip of the form header: "2/4 dự kiến" or "4/4 · kế hoạch đủ buổi". */
export function sessionCounterLabel(plan: PlanProgress | null): string {
  if (plan === null) return "Không gắn kế hoạch";
  const next = Math.min(plan.completed + 1, plan.total);
  return `${next}/${plan.total}${isPlanFull(plan) ? " · kế hoạch đủ buổi" : " dự kiến"}`;
}

function dateProblem(performedOn: string, lastVisit: string | null, today: string): boolean {
  if (!isRealDate(performedOn)) return true;
  if (performedOn > today) return true;
  return lastVisit !== null && performedOn < lastVisit;
}

/**
 * The first problem of the form in the order of the old `save-session`, or null when it can be sent.
 * `lastVisit` is the day (`YYYY-MM-DD`) of the latest completed session of the patient.
 */
export function validateSessionForm(
  form: SessionFormState,
  plan: PlanProgress | null,
  lastVisit: string | null,
  today: string = clinicDateKey(),
): string | null {
  if (isPlanFull(plan)) return PLAN_FULL_MESSAGE;
  if (form.note.trim() === "") return NOTE_REQUIRED_MESSAGE;
  if (form.aftercare.trim() === "") return AFTERCARE_REQUIRED_MESSAGE;
  if (dateProblem(form.performedOn, lastVisit, today)) return DATE_INVALID_MESSAGE;
  if (form.photoName !== "" && !form.photoConsent) return PHOTO_CONSENT_MESSAGE;
  return null;
}

const DAY_MS = 86_400_000;

/** `YYYY-MM-DD` shifted by whole days (calendar arithmetic, no time zone involved). */
export function addDays(dateKey: string, days: number): string {
  return new Date(Date.parse(`${dateKey}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

/** `session-next` default of the old form: today + 30 days. */
export function defaultNextVisit(today: string = clinicDateKey()): string {
  return addDays(today, DEFAULT_NEXT_VISIT_DAYS);
}

/** First photo of an angle is the "before", the following ones are "after" (the old studio's rule). */
export function stageForNewPhoto(existingForView: number): "before" | "after" {
  return existingForView === 0 ? "before" : "after";
}
