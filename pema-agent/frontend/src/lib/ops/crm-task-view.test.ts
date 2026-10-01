import { describe, expect, it } from "vitest";

import {
  channelOfTask,
  defaultNoteFor,
  isManualSend,
  matchesChannel,
  outcomeNeedsNextAction,
  validateResolve,
  type ResolveForm,
} from "./crm-task-view";

const NOW = new Date("2026-09-20T02:00:00Z");

const task = (suggested_action: string, reason = "Việc chăm sóc") => ({ suggested_action, reason });

const form = (patch: Partial<ResolveForm>): ResolveForm => ({
  channel: "call",
  outcome: "no_need",
  note: "Đã trao đổi với khách.",
  nextAction: "",
  hasBooking: false,
  bookingStart: "",
  ...patch,
});

describe("channel of a task", () => {
  it("a_zalo_message_task_is_worked_on_zalo", () => {
    expect(channelOfTask(task("Nhắn Zalo hỏi thăm sau thủ thuật"))).toBe("zalo");
  });

  it("a_call_task_is_worked_by_phone", () => {
    expect(channelOfTask(task("Gọi hỏi thăm tình trạng da"))).toBe("call");
  });

  it("an_sms_task_is_worked_by_sms", () => {
    expect(channelOfTask(task("Gửi SMS nhắc lịch tái khám"))).toBe("sms");
  });

  it("an_unrecognised_task_defaults_to_a_call", () => {
    expect(channelOfTask(task("Xem lại hồ sơ"))).toBe("call");
  });

  it("zalo_and_sms_tasks_are_sent_by_hand", () => {
    expect([isManualSend(task("Nhắn Zalo")), isManualSend(task("Gọi lại"))]).toEqual([true, false]);
  });

  it("the_all_filter_keeps_every_task", () => {
    expect(matchesChannel(task("Gọi lại"), "all")).toBe(true);
  });

  it("a_channel_filter_drops_other_channels", () => {
    expect(matchesChannel(task("Gọi lại"), "zalo")).toBe(false);
  });
});

describe("resolve form", () => {
  it("a_complete_form_has_no_error", () => {
    expect(validateResolve(form({}), NOW)).toBeNull();
  });

  it("a_missing_outcome_is_refused", () => {
    expect(validateResolve(form({ outcome: "" }), NOW)).toBe("Chọn kênh, kết quả và nhập ghi chú.");
  });

  it("a_blank_note_is_refused", () => {
    expect(validateResolve(form({ note: "   " }), NOW)).toBe("Chọn kênh, kết quả và nhập ghi chú.");
  });

  it("an_unanswered_call_needs_a_callback_time", () => {
    expect(validateResolve(form({ outcome: "unanswered" }), NOW)).toBe("Cần ngày giờ gọi lại.");
  });

  it("a_callback_time_in_the_past_is_refused", () => {
    expect(
      validateResolve(form({ outcome: "callback", nextAction: "2026-09-20T08:00" }), NOW),
    ).toBe("Bước tiếp theo phải sau thời điểm hiện tại.");
  });

  it("a_future_callback_time_is_accepted", () => {
    expect(
      validateResolve(form({ outcome: "callback", nextAction: "2026-09-21T09:00" }), NOW),
    ).toBeNull();
  });

  it("agreeing_to_book_needs_the_appointment_time", () => {
    expect(validateResolve(form({ outcome: "booked", hasBooking: true }), NOW)).toBe(
      "Cần nhập ngày giờ lịch hẹn trước khi hoàn tất việc.",
    );
  });

  it("only_unanswered_callback_and_busy_need_a_next_action", () => {
    expect(
      (["unanswered", "callback", "busy", "booked", "no_need"] as const).map(
        outcomeNeedsNextAction,
      ),
    ).toEqual([true, true, true, false, false]);
  });
});

describe("hand-sent shortcut", () => {
  it("a_zalo_task_gets_a_prefilled_note", () => {
    expect(defaultNoteFor("zalo")).toBe("Đã gửi tay qua Zalo theo nội dung gợi ý.");
  });

  it("a_call_task_starts_with_an_empty_note", () => {
    expect(defaultNoteFor("call")).toBe("");
  });
});
