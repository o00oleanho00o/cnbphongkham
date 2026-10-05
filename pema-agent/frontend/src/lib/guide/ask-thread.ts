// State of the "Hỏi Pema" conversation, kept in the page only (nothing is stored: a question may mention a
// customer, so it is not saved anywhere). Pure functions so the page stays a thin shell.
import type { Schemas } from "@/lib/api";

export type AskHit = Schemas["GuideAskHit"];

export type AskTurn = {
  id: number;
  question: string;
  state: "loading" | "done" | "error";
  hits: readonly AskHit[];
  error: string;
};

export const MAX_QUESTION_LENGTH = 500;

/** The question as it is sent: trimmed, blanks collapsed, cut to the length the API accepts; "" when empty. */
export function cleanQuestion(raw: string): string {
  return raw.replace(/\s+/g, " ").trim().slice(0, MAX_QUESTION_LENGTH);
}

export function askedTurn(turns: readonly AskTurn[], id: number, question: string): AskTurn[] {
  return [...turns, { id, question, state: "loading", hits: [], error: "" }];
}

function patched(turns: readonly AskTurn[], id: number, patch: Partial<AskTurn>): AskTurn[] {
  return turns.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn));
}

export const answeredTurn = (
  turns: readonly AskTurn[],
  id: number,
  hits: readonly AskHit[],
): AskTurn[] => patched(turns, id, { state: "done", hits });

export const failedTurn = (turns: readonly AskTurn[], id: number, error: string): AskTurn[] =>
  patched(turns, id, { state: "error", error });

/** Questions staff are likely to have, one tap each (wording of the guide articles). */
export const SUGGESTED_QUESTIONS: readonly string[] = [
  "Làm sao xử lý việc CSKH hôm nay?",
  "Khi nào chuyển phản hồi của khách cho bác sĩ?",
  "Bắt đầu từ đâu theo vai trò của tôi?",
];
