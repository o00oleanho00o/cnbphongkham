import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import {
  NO_IDENTITY_TEXT,
  assignmentErrorText,
  isThreadLocked,
  messageErrorHint,
  messageErrorLabel,
} from "./assignment-errors";

describe("thread_locked", () => {
  const locked = new ApiError(409, "Hoàng Nam đang trả lời — Tiếp quản?", "thread_locked");

  it("is_recognised_by_its_code_and_not_by_the_status", () => {
    expect(isThreadLocked(locked)).toBe(true);
    expect(isThreadLocked(new ApiError(409, "x", "version_conflict"))).toBe(false);
    expect(isThreadLocked(new Error("x"))).toBe(false);
  });

  it("shows_the_sentence_the_backend_sent_with_the_holder_name", () => {
    expect(assignmentErrorText(locked)).toBe("Hoàng Nam đang trả lời — Tiếp quản?");
  });

  it("falls_back_to_a_neutral_name_when_the_backend_sent_no_text", () => {
    expect(assignmentErrorText(new ApiError(409, "", "thread_locked"))).toBe(
      "Đồng nghiệp đang trả lời — Tiếp quản?",
    );
  });
});

describe("no_identity", () => {
  it("is_explained_in_words_that_point_at_the_accounts_page", () => {
    expect(assignmentErrorText(new ApiError(422, "x", "no_identity"))).toBe(NO_IDENTITY_TEXT);
    expect(NO_IDENTITY_TEXT).toContain("Tài khoản Zalo");
  });

  it("gets_its_own_badge_and_hint_on_a_queued_message", () => {
    expect(messageErrorLabel("no_identity")).toBe("Chưa có danh tính gửi");
    expect(messageErrorHint("no_identity")).toBe(NO_IDENTITY_TEXT);
  });
});

describe("other errors", () => {
  it("keep_the_old_badge_and_the_message_of_the_error", () => {
    expect(messageErrorLabel("channel_unavailable")).toBe("Lỗi gửi");
    expect(messageErrorHint("channel_unavailable")).toBeNull();
    expect(assignmentErrorText(new ApiError(500, "Lỗi 500"))).toBe("Lỗi 500");
  });
});
