// Rules of the "Điều chỉnh kế hoạch" form (`plan-edit` modal of prototype/shared/clinic.js): the name and the
// total number of sessions, never below what is done and never above 20. The BE repeats them.
export const MAX_PLAN_SESSIONS = 20;

export type PlanFormState = { title: string; serviceCode: string; total: string; goal: string };

export type PlanStepState = "done" | "next" | "later";

export const TOTAL_BELOW_DONE_MESSAGE = "Tổng số buổi không được thấp hơn số buổi đã hoàn tất.";
export const TOTAL_RANGE_MESSAGE = `Tổng số buổi phải từ 1 đến ${MAX_PLAN_SESSIONS}.`;
export const TITLE_REQUIRED_MESSAGE = "Hãy nhập tên kế hoạch.";
export const SERVICE_REQUIRED_MESSAGE = "Hãy nhập mã dịch vụ.";

/** The first problem of the form, or null. `creating` also asks for the service code. */
export function validatePlanForm(
  form: PlanFormState,
  completed: number,
  creating: boolean,
): string | null {
  if (form.title.trim() === "") return TITLE_REQUIRED_MESSAGE;
  if (creating && form.serviceCode.trim() === "") return SERVICE_REQUIRED_MESSAGE;
  const total = Number(form.total);
  if (!Number.isInteger(total) || total < 1 || total > MAX_PLAN_SESSIONS)
    return TOTAL_RANGE_MESSAGE;
  if (total < completed) return TOTAL_BELOW_DONE_MESSAGE;
  return null;
}

/** One state per planned session, as the old plan tab listed them: done, the next one, the later ones. */
export function planStepStates(completed: number, total: number): PlanStepState[] {
  return Array.from({ length: Math.max(0, total) }, (_unused, index) => {
    if (index < completed) return "done";
    return index === completed ? "next" : "later";
  });
}
