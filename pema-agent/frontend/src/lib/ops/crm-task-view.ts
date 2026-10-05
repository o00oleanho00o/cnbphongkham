// UI-side helpers for "Việc hôm nay". The rules of the CRM (which tasks exist, who may resolve them,
// idempotency, booking in the same transaction) live in the backend; the checks below only repeat the
// validation of the web prototype (prototype/shared/crm-automation.js `validate`) so a staff member gets
// the message before the round trip. The BE answers the same cases with `validation_failed`.
import type { Schemas } from "@/lib/api";
import { foldForSearch } from "@/lib/admin/shared/fold-for-search";

type CrmChannel = Schemas["CrmChannel"];
type CrmOutcome = Schemas["CrmOutcome"];
type CrmTask = Schemas["CrmTaskOut"];

export type ChannelFilter = "all" | CrmChannel;

const CHANNEL_HINTS: { channel: CrmChannel; pattern: RegExp }[] = [
  { channel: "zalo", pattern: /\bzalo\b|nhan tin|tin nhan|nhan cham soc|nhan hoi/ },
  { channel: "sms", pattern: /\bsms\b/ },
  { channel: "call", pattern: /\bgoi\b|dien thoai/ },
];

/**
 * The channel a task is meant to be worked on. `CrmTaskOut` has no channel field yet (open item for B1),
 * so it is read from the Vietnamese `suggested_action` the rules write ("Nhắn Zalo ...", "Gọi ..."). Used
 * only to filter the list and to pre-select the channel of the contact form, never to send anything.
 */
export function channelOfTask(task: Pick<CrmTask, "suggested_action" | "reason">): CrmChannel {
  const text = foldForSearch(`${task.suggested_action} ${task.reason}`);
  return CHANNEL_HINTS.find((hint) => hint.pattern.test(text))?.channel ?? "call";
}

/** A task the staff member sends by hand from the Zalo/SMS app: the text to copy is the point. */
export function isManualSend(task: Pick<CrmTask, "suggested_action" | "reason">): boolean {
  const channel = channelOfTask(task);
  return channel === "zalo" || channel === "sms";
}

export function matchesChannel(
  task: Pick<CrmTask, "suggested_action" | "reason">,
  filter: ChannelFilter,
): boolean {
  return filter === "all" || channelOfTask(task) === filter;
}

const OUTCOMES_NEEDING_NEXT_ACTION: readonly CrmOutcome[] = ["unanswered", "callback", "busy"];

export function outcomeNeedsNextAction(outcome: CrmOutcome | ""): boolean {
  return outcome !== "" && OUTCOMES_NEEDING_NEXT_ACTION.includes(outcome);
}

export type ResolveForm = {
  channel: CrmChannel;
  outcome: CrmOutcome | "";
  note: string;
  /** `datetime-local` value in clinic time, "" when none */
  nextAction: string;
  hasBooking: boolean;
  bookingStart: string;
};

/** First blocking message, or null when the form can be sent. Mirrors the prototype's wording. */
export function validateResolve(form: ResolveForm, now: Date = new Date()): string | null {
  if (!form.outcome || !form.note.trim()) {
    return "Chọn kênh, kết quả và nhập ghi chú.";
  }
  if (form.outcome === "booked" && !form.bookingStart) {
    return "Cần nhập ngày giờ lịch hẹn trước khi hoàn tất việc.";
  }
  if (outcomeNeedsNextAction(form.outcome) && !form.nextAction) {
    return "Cần ngày giờ gọi lại.";
  }
  if (form.nextAction && Date.parse(`${form.nextAction}:00+07:00`) <= now.getTime()) {
    return "Bước tiếp theo phải sau thời điểm hiện tại.";
  }
  if (form.bookingStart && Date.parse(`${form.bookingStart}:00+07:00`) <= now.getTime()) {
    return "Lịch hẹn phải sau thời điểm hiện tại.";
  }
  return null;
}

const DEFAULT_NOTE: Record<CrmChannel, string> = {
  call: "",
  zalo: "Đã gửi tay qua Zalo theo nội dung gợi ý.",
  sms: "Đã gửi tay qua SMS theo nội dung gợi ý.",
  internal_note: "",
};

/** Pre-filled note for the "Đánh dấu đã làm" shortcut of a hand-sent task; the person can edit it. */
export function defaultNoteFor(channel: CrmChannel): string {
  return DEFAULT_NOTE[channel];
}
