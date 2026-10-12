/** Pure helpers of the "Câu hỏi chưa có tài liệu" tab: the filter, the relative time, the starting text of an answer. */
import { formatDate } from "../logic";
import type { Gap, GapState } from "../types";

export const GAP_FILTERS: readonly { id: GapState; label: string }[] = [
  { id: "open", label: "Chưa xử lý" },
  { id: "ignored", label: "Đã bỏ qua" },
  { id: "answered", label: "Đã trả lời" },
];

export const GAPS_EMPTY_TITLE = "Chưa có câu hỏi nào bị bỏ sót";
export const GAPS_EMPTY_HINT =
  "Khi khách hỏi mà agent tra kho không ra kết quả đủ tốt, câu hỏi sẽ hiện ở đây để bạn viết thêm tài liệu.";

const EMPTY_BY_STATE: Record<GapState, string> = {
  open: GAPS_EMPTY_TITLE,
  ignored: "Chưa bỏ qua câu hỏi nào",
  answered: "Chưa có câu hỏi nào được trả lời bằng tài liệu mới",
};

export function emptyTitle(state: GapState): string {
  return EMPTY_BY_STATE[state];
}

/** The text an answer starts from: the question as a heading, ready to be filled in. */
export function answerDraft(question: string): { title: string; text: string } {
  const title = question.trim();
  return { title, text: `# ${title}\n\n` };
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "vừa xong", "5 phút trước", "3 giờ trước", "hôm qua", "4 ngày trước", then the date from 30 days on. */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return formatDate(iso);
  const age = now.getTime() - then;
  if (age < MINUTE) return "vừa xong";
  if (age < HOUR) return `${Math.floor(age / MINUTE)} phút trước`;
  if (age < DAY) return `${Math.floor(age / HOUR)} giờ trước`;
  if (age < 2 * DAY) return "hôm qua";
  if (age < 30 * DAY) return `${Math.floor(age / DAY)} ngày trước`;
  return formatDate(iso);
}

/** "7 lần" */
export function countText(count: number): string {
  return `${count} lần`;
}

/** The list without one gap: the row leaves at once, the reload confirms it. */
export function withoutGap(gaps: readonly Gap[], id: string): Gap[] {
  return gaps.filter((gap) => gap.id !== id);
}
