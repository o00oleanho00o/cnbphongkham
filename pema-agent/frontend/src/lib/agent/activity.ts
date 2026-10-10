// What the agent did, as `GET /v1/admin/sessions|traces|usage` answer it, and the rules the pages show it by: the
// words of a turn's outcome and of each step, the size of a duration or of a count of tokens, the totals of a usage
// chart. The trace holds timings, tokens and outcomes only; the words of a conversation are in the session.

export interface Paged<T> {
  items: T[];
  has_more: boolean;
}

export interface SessionRow {
  session_id: string;
  channel: string | null;
  user_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
  compacted: boolean;
}

export interface SessionMessage {
  role: string;
  text: string;
  tools: string[];
  at: string;
}

export interface SessionDetail {
  session_id: string;
  channel: string | null;
  user_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
  summary: string | null;
  messages: SessionMessage[];
}

export interface TurnRow {
  turn_id: string;
  session_id: string;
  channel: string | null;
  user_id: string | null;
  model: string;
  started_at: string;
  duration_ms: number;
  stop: string;
  steps: number;
  error_kind: string | null;
  input_tokens: number;
  output_tokens: number;
}

export interface TurnEvent {
  kind: string;
  step: number;
  name: string;
  duration_ms: number;
  is_error: boolean;
  detail: Record<string, unknown>;
}

export interface TurnDetail extends TurnRow {
  compactions: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  reasoning_tokens: number;
  events: TurnEvent[];
}

export interface UsageDay {
  day: string;
  turns: number;
  failed: number;
  input_tokens: number;
  output_tokens: number;
}

export interface Usage {
  today: string | null;
  days: UsageDay[];
}

export const SESSIONS_PATH = "/v1/admin/sessions";
export const TRACES_PATH = "/v1/admin/traces";
export const USAGE_PATH = "/v1/admin/usage";
export const SESSIONS_HREF = "/admin/agent/sessions";
export const TRACES_HREF = "/admin/agent/traces";

/** The address of the sessions page already filtered to one chat (and of the trace page likewise). */
export function sessionHref(sessionId: string): string {
  return `${SESSIONS_HREF}?session=${encodeURIComponent(sessionId)}`;
}

export function tracesOfSessionHref(sessionId: string): string {
  return `${TRACES_HREF}?session=${encodeURIComponent(sessionId)}`;
}

const STOP_LABEL: Readonly<Record<string, string>> = {
  completed: "Xong",
  max_steps: "Hết số bước",
  deadline: "Quá thời gian",
  budget: "Hết ngân sách",
  loop: "Lặp vòng",
  error: "Lỗi",
};

export function stopLabel(stop: string): string {
  return STOP_LABEL[stop] ?? stop;
}

const ERROR_LABEL: Readonly<Record<string, string>> = {
  config: "Chưa cấu hình model",
  auth: "Khóa API sai hoặc hết hạn",
  rate_limit: "Nhà cung cấp giới hạn số lần gọi",
  context_overflow: "Cuộc trò chuyện quá dài",
  transient: "Nhà cung cấp tạm lỗi",
  empty_response: "Model trả lời rỗng",
  unknown: "Lỗi không rõ",
};

/** The reason a turn failed in words; "" when it did not. */
export function errorLabel(kind: string | null): string {
  if (kind === null) return "";
  return ERROR_LABEL[kind] ?? kind;
}

const EVENT_LABEL: Readonly<Record<string, string>> = {
  model_call: "Gọi model",
  model_retry: "Gọi lại model",
  tool_call: "Gọi tool",
  guard: "Chặn bởi guard",
  inbox: "Tin đến giữa lượt",
  compaction: "Rút gọn ngữ cảnh",
  memory_flush: "Ghi nhớ",
  repair: "Sửa lỗi lệnh gọi tool",
};

export function eventLabel(kind: string): string {
  return EVENT_LABEL[kind] ?? kind;
}

/** "320 ms", "1,5 s", "2 phút 5 s". */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1).replace(".", ",")} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} phút ${Math.round(seconds - minutes * 60)} s`;
}

/** "1.234" for a count of tokens, in the Vietnamese grouping. */
export function formatCount(count: number): string {
  return count.toLocaleString("vi-VN");
}

export function totalTokens(turn: { input_tokens: number; output_tokens: number }): number {
  return turn.input_tokens + turn.output_tokens;
}

export interface UsageTotals {
  turns: number;
  failed: number;
  tokens: number;
}

/** Totals of the days of a usage listing; the last day is today. */
export function usageTotals(days: readonly UsageDay[]): UsageTotals {
  return days.reduce<UsageTotals>(
    (sum, day) => ({
      turns: sum.turns + day.turns,
      failed: sum.failed + day.failed,
      tokens: sum.tokens + day.input_tokens + day.output_tokens,
    }),
    { turns: 0, failed: 0, tokens: 0 },
  );
}

/** What a user and a channel are called in a list: the user id, else the session id. */
export function sessionTitle(row: Pick<SessionRow, "user_id" | "session_id">): string {
  return row.user_id ?? row.session_id;
}

/** "size: 12 · reason: x" for the metadata of a step; nested values go in as JSON. */
export function detailText(detail: Record<string, unknown>): string {
  return Object.entries(detail)
    .map(
      ([key, value]) =>
        `${key}: ${typeof value === "object" ? JSON.stringify(value) : String(value)}`,
    )
    .join(" · ");
}

/** `path?a=1&b=2` without the parameters that are empty, false or 0 (the agent's defaults). */
export function listPath(base: string, params: Record<string, string | number | boolean>): string {
  const query = Object.entries(params)
    .filter(([, value]) => value !== "" && value !== false && value !== 0)
    .map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`)
    .join("&");
  return query === "" ? base : `${base}?${query}`;
}
