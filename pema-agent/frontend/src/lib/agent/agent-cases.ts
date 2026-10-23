// The agent's cases (proactive work of its plugins: appointment reminders, follow-ups) as `GET /v1/admin/cases`
// lists them, and the words the Ca page shows for them. "Run now" wakes a live case: its checks still run.

export type CaseStatus = "open" | "waiting" | "needs_human" | "done" | "stopped";

export interface AgentCase {
  id: number;
  kind: string;
  key: string;
  channel: string;
  conversation_id: string;
  goal: string;
  status: CaseStatus;
  node: string;
  state: Record<string, unknown>;
  wait_for: string | null;
  wake_at: string | null;
  deadline: string | null;
  turns: number;
  proactive_sent: number;
  end_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
  closed_at: string | null;
}

export interface CaseEvent {
  seq: number;
  at: string;
  kind: string;
  node: string | null;
  detail: Record<string, unknown>;
}

export const CASES_PATH = "/v1/admin/cases";

export const casePath = (id: number) => `${CASES_PATH}/${id}`;

export const wakePath = (id: number) => `${casePath(id)}/wake`;

export const STATUS_LABELS: Record<CaseStatus, string> = {
  open: "Đang chạy",
  waiting: "Đang chờ",
  needs_human: "Cần nhân viên",
  done: "Xong",
  stopped: "Đã dừng",
};

export const KIND_LABELS: Record<string, string> = {
  follow_up: "Chăm sóc lại",
  reminder: "Nhắc lịch",
};

export const WAIT_LABELS: Record<string, string> = {
  clock: "tới giờ",
  customer: "khách nhắn",
  event: "sự kiện",
};

export const isLive = (item: AgentCase) => item.status === "open" || item.status === "waiting";

export function isCaseList(value: unknown): value is { cases: AgentCase[] } {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as { cases?: unknown }).cases)
  );
}

export const EVENT_LABELS: Record<string, string> = {
  opened: "Mở ca",
  woken: "Đánh thức",
  blocked: "Bị chặn",
  sent: "Đã nhắn",
  decision: "Quyết định",
  stopped: "Dừng",
  error: "Lỗi",
  lost: "Bỏ (lượt khác đã đổi ca)",
};
