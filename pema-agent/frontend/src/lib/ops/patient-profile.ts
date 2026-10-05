// Pure rules of the Patient 360 dialogs of package U, step U9. The backend owns every rule; this file words the
// sentences of the old Clinic Web (`prototype/shared/clinic.js`, `crm-automation.js`, `care-finance.js`) and checks a
// form BEFORE it is sent, so a mistake is told in place; the BE answer stays the last word.
import type { Schemas } from "@/lib/api";
import { EXPECTED_SOURCE_LABEL } from "@/lib/ops/labels";

export const MAX_ALERTS = 20;
export const MAX_ALERT_CHARS = 200;
export const MAX_SERVICE_SESSIONS = 20;

export const BRIEF_BLANK = "Brief không được để trống.";
export const AFTERCARE_BLANK = "Hãy nhập hướng dẫn.";
export const MESSAGE_BLANK = "Hãy nhập nội dung tin nhắn.";
export const CLINICAL_NOTE_BLANK = "Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.";
export const EXPECTED_RETURN_INVALID = "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.";
export const NAME_REQUIRED = "Nhập tên người bệnh";
export const NO_CLIPBOARD = "Không truy cập được clipboard; hãy chọn và sao chép văn bản.";

/** Sources a person may type for the expected return: the old list without `appointment`. */
export const EXPECTED_SOURCE_OPTIONS: readonly { value: string; label: string }[] = [
  "doctor_recommendation",
  "service_protocol",
  "treatment_plan",
  "followup_automation",
].map((value) => ({ value, label: EXPECTED_SOURCE_LABEL[value] ?? value }));

/** Old `alerts-edit`: one warning per line, trimmed, blank lines dropped. */
export function splitAlerts(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

export function alertsProblem(lines: readonly string[]): string | null {
  if (lines.length > MAX_ALERTS) return `Tối đa ${MAX_ALERTS} cảnh báo.`;
  if (lines.some((line) => line.length > MAX_ALERT_CHARS))
    return `Mỗi cảnh báo tối đa ${MAX_ALERT_CHARS} ký tự.`;
  return null;
}

/** True for a real calendar day written `YYYY-MM-DD` (2026-02-30 is not one). */
export function isIsoDay(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (match === null) return false;
  const [year, month, day] = match.slice(1).map(Number);
  if (year === undefined || month === undefined || day === undefined) return false;
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
}

/** Same test as the old `expected()`: a real day, a reason that is not blank, a typed source. */
export function expectedReturnProblem(form: {
  date: string;
  reason: string;
  source: string;
}): string | null {
  const sourceOk = EXPECTED_SOURCE_OPTIONS.some((option) => option.value === form.source);
  if (!isIsoDay(form.date) || form.reason.trim() === "" || !sourceOk)
    return EXPECTED_RETURN_INVALID;
  return null;
}

export type ServicePlanForm = { serviceId: string; sessions: string; discount: string };

export type ParsedServicePlan =
  { ok: true; body: Schemas["ServicePlanCreate"] } | { ok: false; problem: string };

/** Old `linked-service-form`: a service, 1 to 20 sessions, a discount of whole dong from 0. */
export function parseServicePlanForm(form: ServicePlanForm): ParsedServicePlan {
  if (form.serviceId === "") return { ok: false, problem: "Chọn dịch vụ." };
  const sessions = Number(form.sessions);
  if (!Number.isInteger(sessions) || sessions < 1 || sessions > MAX_SERVICE_SESSIONS)
    return { ok: false, problem: `Số buổi từ 1 đến ${MAX_SERVICE_SESSIONS}.` };
  const text = form.discount.trim() === "" ? "0" : form.discount.trim();
  const discount = Number(text);
  if (!Number.isInteger(discount) || discount < 0)
    return { ok: false, problem: "Giảm giá là số tiền từ 0 ₫." };
  return { ok: true, body: { service_id: form.serviceId, sessions, discount_vnd: discount } };
}

/** The status words of a course on the finance tab. */
export function planStatusLine(status: string): string {
  return status === "completed"
    ? "Hoàn tất"
    : status === "active"
      ? "Đang thực hiện"
      : "Chưa bắt đầu";
}
