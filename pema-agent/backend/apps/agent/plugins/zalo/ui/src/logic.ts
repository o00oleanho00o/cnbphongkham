/** The pages' rules, free of the dashboard so tests run them alone. */
import type { Account, AccountUpdate, AllowlistMode, ChannelKind, OaKeys, QrState, QrStatus } from "./types";

export const ACCOUNT_ID = /^[a-z0-9][a-z0-9-]*$/;
export const MAX_ACCOUNT_ID = 58;

export const CHANNEL_LABEL: Record<ChannelKind, string> = {
  zalo_personal: "Nick cá nhân",
  zalo_bot: "Bot chính thức",
  zalo_oa: "Zalo OA",
};

export const CHANNEL_HINT: Record<ChannelKind, string> = {
  zalo_personal:
    "Dùng nick Zalo thật qua giao thức không chính thức (đăng nhập bằng mã QR) - đủ tính năng nhất nhưng CÓ " +
    "rủi ro bị Zalo khóa. Chỉ dùng nick phụ.",
  zalo_bot:
    "Token từ Zalo Bot Creator. Không gửi được file, không thả cảm xúc, không tag và không đọc được thành viên " +
    "nhóm - giới hạn của Zalo Bot API. Đổi lại không có rủi ro bị khóa.",
  zalo_oa: "Official Account: lưu được khóa OA, nhưng kênh OA chưa chạy ở phiên bản này.",
};

/** Bots and OAs start closed: anyone with the link can write to them, a personal nick needs to be a friend. */
export const DEFAULT_ALLOWLIST: Record<ChannelKind, AllowlistMode> = {
  zalo_personal: "all",
  zalo_bot: "list",
  zalo_oa: "list",
};

export interface AccountForm {
  id: string;
  label: string;
  channel: ChannelKind;
  allowlistMode: AllowlistMode;
  allowlistIds: string;
  respondToGroups: boolean;
  groupRequireMention: boolean;
  groupPassiveListen: boolean;
  typingIndicator: boolean;
  autoReact: boolean;
  autoReactIcon: string;
  autoAcceptFriends: boolean;
  autoAcceptDelay: number;
  disabledTools: string[];
  /** A new personal nick: the person ticked that zca-js is unofficial and the nick can be locked. */
  riskAccepted: boolean;
}

export const PERSONAL_RISK =
  "Tôi hiểu nick cá nhân chạy qua giao thức không chính thức (zca-js): Zalo có thể khóa nick. Tôi dùng nick phụ.";

export function formOf(account: Account | null): AccountForm {
  const channel = account?.channel ?? "zalo_personal";
  return {
    id: account?.id ?? "",
    label: account?.label ?? "",
    channel,
    allowlistMode: account?.allowlist.mode ?? DEFAULT_ALLOWLIST[channel],
    allowlistIds: (account?.allowlist.user_ids ?? []).join("\n"),
    respondToGroups: account?.respond_to_groups ?? true,
    groupRequireMention: account?.group_require_mention ?? true,
    groupPassiveListen: account?.group_passive_listen ?? true,
    typingIndicator: account?.typing_indicator_enabled ?? true,
    autoReact: account?.auto_react_enabled ?? true,
    autoReactIcon: account?.auto_react_icon ?? "heart",
    autoAcceptFriends: account?.auto_accept_friends ?? false,
    autoAcceptDelay: account?.auto_accept_friend_delay_minutes ?? 1,
    disabledTools: account?.disabled_tools ?? [],
    riskAccepted: false,
  };
}

export function withChannel(form: AccountForm, channel: ChannelKind): AccountForm {
  return { ...form, channel, allowlistMode: DEFAULT_ALLOWLIST[channel] };
}

/** One Zalo user id per line; commas and spaces separate too, repeats count once. */
export function parseIds(text: string): string[] {
  return [...new Set(text.split(/[\s,;]+/).filter(Boolean))];
}

export function patchOf(form: AccountForm): AccountUpdate {
  return {
    label: form.label.trim(),
    allowlist: { mode: form.allowlistMode, user_ids: parseIds(form.allowlistIds) },
    respond_to_groups: form.respondToGroups,
    group_require_mention: form.groupRequireMention,
    group_passive_listen: form.groupPassiveListen,
    typing_indicator_enabled: form.typingIndicator,
    auto_react_enabled: form.autoReact,
    auto_react_icon: form.autoReactIcon,
    auto_accept_friends: form.autoAcceptFriends,
    auto_accept_friend_delay_minutes: clampDelay(form.autoAcceptDelay),
    disabled_tools: [...form.disabledTools].sort(),
  };
}

export function clampDelay(minutes: number): number {
  return Number.isFinite(minutes) ? Math.max(0, Math.min(1440, Math.round(minutes))) : 0;
}

/** What blocks saving, in the words the person reads; null when the form can go. */
export function formProblem(form: AccountForm, creating: boolean): string | null {
  if (creating && !ACCOUNT_ID.test(form.id)) return "ID chỉ gồm chữ thường, số và dấu gạch ngang (vd: nick-cham-soc).";
  if (creating && form.id.length > MAX_ACCOUNT_ID) return `ID tối đa ${MAX_ACCOUNT_ID} ký tự.`;
  if (creating && form.channel === "zalo_personal" && !form.riskAccepted) {
    return "Đánh dấu ô xác nhận rủi ro để thêm nick cá nhân.";
  }
  if (!form.label.trim()) return "Nhập tên hiển thị.";
  if (form.label.trim().length > 100) return "Tên hiển thị tối đa 100 ký tự.";
  const bad = parseIds(form.allowlistIds).find((uid) => !ZALO_ID.test(uid));
  if (form.allowlistMode === "list" && bad) return `User ID không hợp lệ: ${bad}`;
  return null;
}

export const ZALO_ID = /^[A-Za-z0-9_.-]{1,100}$/;

/** The account's list after letting one user in or out (the mode is left as it is). */
export function toggledIds(ids: readonly string[], uid: string, allowed: boolean): string[] {
  const rest = ids.filter((id) => id !== uid);
  return allowed ? [...rest, uid] : rest;
}

export const EMPTY_OA_KEYS: OaKeys = { app_id: "", app_secret: "", oa_secret_key: "", refresh_token: "" };

/** OA keys go together: all four, or none (keep what is stored). */
export function oaKeysState(keys: OaKeys): "empty" | "partial" | "complete" {
  const filled = Object.values(keys).filter((v) => v.trim() !== "").length;
  if (filled === 0) return "empty";
  return filled === Object.keys(keys).length ? "complete" : "partial";
}

export const QR_TEXT: Record<QrState | "starting", string> = {
  idle: "Đang chuẩn bị...",
  starting: "Đang tạo mã QR...",
  waiting_scan: "Mở app Zalo trên điện thoại và quét mã này",
  scanned: "Đã quét - xác nhận đăng nhập trên điện thoại",
  success: "Đăng nhập thành công, kênh đang khởi động",
  expired: "Hết thời gian chờ quét",
  error: "Đăng nhập thất bại",
};

export interface QrView {
  state: QrState | "starting";
  image: string | null;
  error: string | null;
  done: boolean;
}

export function qrView(status: QrStatus): QrView {
  return {
    state: status.state,
    image:
      status.state === "waiting_scan" && status.qr_png_base64
        ? `data:image/png;base64,${status.qr_png_base64}`
        : null,
    error: status.state === "error" ? (status.detail ?? null) : null,
    done: status.state === "success" || status.state === "expired" || status.state === "error",
  };
}

export function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("vi-VN");
}
