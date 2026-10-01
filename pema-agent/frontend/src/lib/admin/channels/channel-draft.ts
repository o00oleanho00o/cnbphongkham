// New in Pema (no zalo-agent original): the editable draft of one channel card of the switchboard and
// its validation. Pure, so it is tested without React. Limits mirror `ChannelSettingsUpdate` in the
// contract (`daily_cap` 0..1000, gaps 0..3600 s, `HH:MM` window); the BE validates again.
//
// `PUT /admin/channels/{channel}` treats a null/absent field as "unchanged", so a value that was set
// can be changed but not cleared. The draft therefore refuses an empty field when the channel already
// has a value, instead of silently sending nothing.
import type { Schemas } from "@/lib/api";

type ChannelSettings = Schemas["ChannelSettingsOut"];
export type ChannelFields = Omit<Schemas["ChannelSettingsUpdate"], "version" | "enabled">;

export type ChannelDraft = {
  dailyCap: string;
  minGap: string;
  maxGap: string;
  windowStart: string;
  windowEnd: string;
};

export type DraftResult = { ok: true; fields: ChannelFields } | { ok: false; error: string };

export const MAX_DAILY_CAP = 1000;
export const MAX_GAP_SECONDS = 3600;

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
const DIGITS_PATTERN = /^\d+$/;

export function draftFromChannel(c: ChannelSettings): ChannelDraft {
  return {
    dailyCap: c.daily_cap === null || c.daily_cap === undefined ? "" : String(c.daily_cap),
    minGap: String(c.min_gap_seconds),
    maxGap: String(c.max_gap_seconds),
    windowStart: c.send_window_start ?? "",
    windowEnd: c.send_window_end ?? "",
  };
}

type Parsed = { ok: true; value: number } | { ok: false; error: string };

function parseWhole(raw: string, max: number, label: string): Parsed {
  const text = raw.trim();
  if (!DIGITS_PATTERN.test(text))
    return { ok: false, error: `${label}: nhập số nguyên từ 0 đến ${max}.` };
  const value = Number.parseInt(text, 10);
  if (value > max) return { ok: false, error: `${label}: tối đa ${max}.` };
  return { ok: true, value };
}

/** Các trường đã đổi so với giá trị đang lưu; lỗi đầu tiên nếu có trường không hợp lệ. */
export function buildFields(draft: ChannelDraft, current: ChannelSettings): DraftResult {
  const fields: ChannelFields = {};

  const capText = draft.dailyCap.trim();
  if (capText === "" && current.daily_cap !== null && current.daily_cap !== undefined) {
    return {
      ok: false,
      error:
        "Trần mỗi ngày: nhập 0 để không gửi chủ động nào, hoặc một số khác (không bỏ trống được).",
    };
  }
  if (capText !== "") {
    const cap = parseWhole(capText, MAX_DAILY_CAP, "Trần mỗi ngày");
    if (!cap.ok) return cap;
    if (cap.value !== current.daily_cap) fields.daily_cap = cap.value;
  }

  const min = parseWhole(draft.minGap, MAX_GAP_SECONDS, "Cách nhau tối thiểu");
  if (!min.ok) return min;
  const max = parseWhole(draft.maxGap, MAX_GAP_SECONDS, "Cách nhau tối đa");
  if (!max.ok) return max;
  if (min.value > max.value) {
    return { ok: false, error: "Cách nhau tối thiểu không được lớn hơn tối đa." };
  }
  if (min.value !== current.min_gap_seconds) fields.min_gap_seconds = min.value;
  if (max.value !== current.max_gap_seconds) fields.max_gap_seconds = max.value;

  const start = draft.windowStart.trim();
  const end = draft.windowEnd.trim();
  const hasWindow = start !== "" || end !== "";
  if (!hasWindow && (current.send_window_start || current.send_window_end)) {
    return { ok: false, error: "Khung giờ gửi: chọn giờ mới (không bỏ trống được)." };
  }
  if (hasWindow && (start === "" || end === "")) {
    return { ok: false, error: "Khung giờ gửi: nhập cả giờ bắt đầu và giờ kết thúc." };
  }
  if (hasWindow && !(TIME_PATTERN.test(start) && TIME_PATTERN.test(end))) {
    return { ok: false, error: "Khung giờ gửi: giờ phải có dạng HH:MM." };
  }
  if (hasWindow && start !== current.send_window_start) fields.send_window_start = start;
  if (hasWindow && end !== current.send_window_end) fields.send_window_end = end;

  return { ok: true, fields };
}

/** Có gì để lưu không (nút Lưu sáng lên khi true). Lỗi nhập cũng tính là "có thay đổi". */
export function hasChanges(draft: ChannelDraft, current: ChannelSettings): boolean {
  const result = buildFields(draft, current);
  if (!result.ok) return true;
  return Object.keys(result.fields).length > 0;
}

/** Tỷ lệ đã dùng trong ngày, 0..1; trần 0 hoặc không có trần thì không có thanh. */
export function usageRatio(sent: number, cap: number | null | undefined): number | null {
  if (cap === null || cap === undefined || cap <= 0) return null;
  return Math.min(1, sent / cap);
}
