// Words for the errors of the shared Inbox. The BE sends a Vietnamese message with every error; these cover the
// two codes the screen must treat in its own way: `thread_locked` (somebody else holds the thread) and
// `no_identity` (the thread is on no clinic identity, so nothing can be sent). Pure, so they are tested alone.
import { ApiError, errorMessage } from "@/lib/api/client";
import { lockedNotice } from "@/lib/ops/inbox-view";

export const NO_IDENTITY_TEXT =
  "Chưa gửi được: hội thoại này chưa gắn với tài khoản Zalo nào. Nhờ chủ phòng khám hoặc quản lý kiểm tra ở Tài khoản Zalo.";

export const THREAD_LOCKED_UNSENT = "Tin chưa gửi. Nội dung bạn soạn vẫn còn.";

export function isThreadLocked(error: unknown): boolean {
  return error instanceof ApiError && error.code === "thread_locked";
}

/** The sentence to show for a caught error; the BE's own message wins when it sent one. */
export function assignmentErrorText(error: unknown): string {
  if (error instanceof ApiError && error.code === "thread_locked") {
    return error.message || lockedNotice(null);
  }
  if (error instanceof ApiError && error.code === "no_identity") return NO_IDENTITY_TEXT;
  return errorMessage(error);
}

const MESSAGE_ERROR_LABEL: Record<string, string> = {
  no_identity: "Chưa có danh tính gửi",
  thread_locked: "Bị khóa: có người khác phụ trách",
};

/** Badge text of an outbound message that carries an `error_code`. */
export function messageErrorLabel(code: string): string {
  return MESSAGE_ERROR_LABEL[code] ?? "Lỗi gửi";
}

/** Longer line under such a message; null when the badge says enough. */
export function messageErrorHint(code: string): string | null {
  if (code === "no_identity") return NO_IDENTITY_TEXT;
  return null;
}
