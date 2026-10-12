/** Pure helpers of the "Thử tìm" tab: the channel choice, the source behind a chunk, how a stage and a score read. */
import type { SearchDebugQuery, SearchStage } from "../types";

export const CHANNEL_OPTIONS: readonly { value: SearchDebugQuery["channel"]; label: string }[] = [
  { value: "patient", label: "Bệnh nhân" },
  { value: "staff", label: "Nhân viên" },
];

export const PATIENT_CHANNEL_HINT =
  "Như kênh bệnh nhân: nguồn nội bộ và nguồn hết hiệu lực vào ngày hỏi bị ẩn, đúng như agent thật.";

/** The id of the source a chunk belongs to: chunk ids look like `<sourceId>-c<n>`; null when it does not. */
export function sourceIdOf(chunkId: string): string | null {
  const match = /^(.+)-c\d+$/.exec(chunkId);
  return match?.[1] ?? null;
}

/** Only the last stage (what the agent gets) starts open. */
export function startsOpen(stageId: string): boolean {
  return stageId === "final";
}

/** The stages have no candidate list of their own to show, only their note. */
export function listsCandidates(stageId: string): boolean {
  return stageId !== "understand";
}

export function isBlankQuestion(question: string): boolean {
  return question.trim().length === 0;
}

/** "12 ms", or "1,2 s" from 1000 ms. */
export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
}

const SCORE_LABEL: Record<string, string> = {
  keyword: "điểm",
  vector: "độ giống",
  fused: "điểm",
  reranked: "điểm xếp lại",
  final: "điểm",
};

export function scoreLabel(stageId: string): string {
  return SCORE_LABEL[stageId] ?? "điểm";
}

const SCORE_DIGITS: Record<string, number> = { vector: 3, fused: 3 };

/** Similarities (and the ranking that follows them) keep three decimals, the other scores two; the comma is the decimal mark. */
export function formatScore(stageId: string, score: number): string {
  return score.toFixed(SCORE_DIGITS[stageId] ?? 2).replace(".", ",");
}

/** The sentence under a stage title: the note, or what a skipped or empty stage means. */
export function stageSummary(stage: SearchStage): string {
  if (stage.note) return stage.note;
  return stage.skipped ? "Bỏ qua bước này" : "";
}

/** "3 ứng viên" / "bỏ qua" / "không có ứng viên", the short word on a stage header. */
export function stageCount(stage: SearchStage): string {
  if (stage.skipped) return "bỏ qua";
  if (!listsCandidates(stage.id)) return "";
  return stage.candidates.length === 0 ? "không có ứng viên" : `${stage.candidates.length} ứng viên`;
}
