// The matrix editor keeps typed numbers as text while a person types ("0," on the way to "0,85") and turns them
// into the contract's numbers only when saving. The limits are the contract's (`pema_contracts/care.py`); the
// backend validates again and the thresholds themselves are the doctor's decision, never this file's.
import type { CareMatrix, CareMatrixIn } from "@/lib/care/care-types";
import { parseBounded } from "@/lib/care/forms";

export type MatrixText = {
  handoffConfidence: string;
  windowHours: string;
  repeatThreshold: string;
  autonomyConfidence: string;
  /** `n_to_l2` per action type; empty text means "none" */
  nToL2: Record<string, string>;
};

export type MatrixEdit = { handoff: CareMatrix["handoff"]; autonomy: CareMatrix["autonomy"] };

export function textOf(matrix: CareMatrix): MatrixText {
  return {
    handoffConfidence: String(matrix.handoff.confidence_threshold),
    windowHours: String(matrix.handoff.post_procedure_window_hours),
    repeatThreshold: String(matrix.handoff.repeat_question_threshold),
    autonomyConfidence: String(matrix.autonomy.confidence_threshold),
    nToL2: Object.fromEntries(
      matrix.autonomy.rules.map((rule) => [
        rule.action_type,
        rule.n_to_l2 === null ? "" : String(rule.n_to_l2),
      ]),
    ),
  };
}

export function editOf(matrix: CareMatrix): MatrixEdit {
  return { handoff: matrix.handoff, autonomy: matrix.autonomy };
}

type Built = { value: CareMatrixIn; error: "" } | { value: null; error: string };

function wholeNumber(raw: string, min: number, max: number): number | null {
  const value = parseBounded(raw, min, max);
  return value !== null && Number.isInteger(value) ? value : null;
}

function nValues(
  edit: MatrixEdit,
  text: MatrixText,
): { values: Map<string, number | null>; error: string } {
  const entries = edit.autonomy.rules.map((rule) => {
    const raw = (text.nToL2[rule.action_type] ?? "").trim();
    if (rule.hard_human || raw === "") return [rule.action_type, null, ""] as const;
    const value = wholeNumber(raw, 1, 1000);
    return [rule.action_type, value, value === null ? rule.action_type : ""] as const;
  });
  const bad = entries.find((entry) => entry[2] !== "");
  return {
    values: new Map(entries.map((entry) => [entry[0], entry[1]])),
    error: bad ? "Số lần duyệt không sửa để lên L2 là số nguyên từ 1 đến 1000, hoặc để trống." : "",
  };
}

/** The body of the save call from the typed state, or the first thing that is not a number. */
export function buildMatrix(base: CareMatrix, edit: MatrixEdit, text: MatrixText): Built {
  const handoffConfidence = parseBounded(text.handoffConfidence, 0, 1);
  if (handoffConfidence === null)
    return { value: null, error: "Ngưỡng tin cậy của agent là số từ 0 đến 1." };
  const windowHours = wholeNumber(text.windowHours, 0, 720);
  if (windowHours === null)
    return { value: null, error: "Cửa sổ sau thủ thuật là số giờ từ 0 đến 720." };
  const repeat = wholeNumber(text.repeatThreshold, 2, 10);
  if (repeat === null)
    return { value: null, error: "Số lần hỏi lặp lại là số nguyên từ 2 đến 10." };
  const autonomyConfidence = parseBounded(text.autonomyConfidence, 0, 1);
  if (autonomyConfidence === null)
    return { value: null, error: "Ngưỡng tin cậy để tự trả lời là số từ 0 đến 1." };
  const n = nValues(edit, text);
  if (n.error) return { value: null, error: n.error };
  return {
    error: "",
    value: {
      version: base.version,
      handoff: {
        ...edit.handoff,
        confidence_threshold: handoffConfidence,
        post_procedure_window_hours: windowHours,
        repeat_question_threshold: repeat,
      },
      autonomy: {
        ...edit.autonomy,
        confidence_threshold: autonomyConfidence,
        rules: edit.autonomy.rules.map((rule) => ({
          ...rule,
          n_to_l2: n.values.get(rule.action_type) ?? null,
        })),
      },
    },
  };
}
