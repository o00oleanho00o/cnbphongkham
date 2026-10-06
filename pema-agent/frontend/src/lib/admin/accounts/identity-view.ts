// Words and checks for the clinic identities on the accounts page (package O, frames WM24-WM29). Pure, so the
// sentences and the form rules are tested without a screen. The BE owns the real rules (purpose change refused
// while conversations point at the identity, limit ranges); the form only stops what it can see is wrong.
import type { Schemas } from "@/lib/api";

type Identity = Schemas["IdentityOut"];
type Settings = Schemas["NotifySettingsOut"];

export const PURPOSE_LABEL: Record<Schemas["IdentityPurpose"], string> = {
  customer: "Khách hàng",
  internal: "Nội bộ",
};

export const PURPOSE_OPTIONS: { id: Schemas["IdentityPurpose"]; title: string; hint: string }[] = [
  { id: "customer", title: "Khách hàng", hint: "nhắn tin với khách" },
  { id: "internal", title: "Nội bộ", hint: "chỉ gửi thông báo cho nhân viên" },
];

export const GAP_MAX_S = 3600;
export const DAILY_CAP_MAX = 1000;

/** "tối đa 5 tin chủ động/ngày · cách nhau 60–240 giây (theo kênh)". */
export function limitsText(identity: Pick<Identity, "effective" | "overrides">): string {
  const { daily_cap: cap, send_gap_min_s: min, send_gap_max_s: max } = identity.effective;
  const own = Object.values(identity.overrides).some((v) => v !== null && v !== undefined);
  const capText =
    cap === null || cap === undefined
      ? "không giới hạn tin chủ động/ngày"
      : `tối đa ${cap} tin chủ động/ngày`;
  return `${capText} · cách nhau ${min}–${max} giây (${own ? "riêng" : "theo kênh"})`;
}

/** "Hoàng Nam", "Hoàng Nam, Mai Anh" or null when nobody is on duty. */
export function onDutyText(operators: readonly { name: string }[]): string | null {
  return operators.length === 0 ? null : operators.map((o) => o.name).join(", ");
}

export type IdentityForm = {
  label: string;
  purpose: Schemas["IdentityPurpose"];
  dailyCap: string;
  gapMin: string;
  gapMax: string;
};

const textOf = (v: number | null | undefined): string =>
  v === null || v === undefined ? "" : String(v);

export function formOf(identity: Identity): IdentityForm {
  return {
    label: identity.label,
    purpose: identity.purpose,
    dailyCap: textOf(identity.overrides.daily_cap),
    gapMin: textOf(identity.overrides.send_gap_min_s),
    gapMax: textOf(identity.overrides.send_gap_max_s),
  };
}

/** A blank box clears the override (null); anything else must be a whole number in range, else undefined. */
export function parseLimit(raw: string, max: number): number | null | undefined {
  const text = raw.trim();
  if (text === "") return null;
  const value = Number(text);
  const valid = Number.isInteger(value) && value >= 0 && value <= max;
  return valid ? value : undefined;
}

export type IdentityErrors = Partial<Record<"label" | "dailyCap" | "gapMin" | "gapMax", string>>;

export function validateForm(form: IdentityForm): IdentityErrors {
  const cap = parseLimit(form.dailyCap, DAILY_CAP_MAX);
  const min = parseLimit(form.gapMin, GAP_MAX_S);
  const max = parseLimit(form.gapMax, GAP_MAX_S);
  const gapsOrdered = typeof min === "number" && typeof max === "number" && min > max;
  return {
    ...(form.label.trim() === "" ? { label: "Nhập tên danh tính." } : {}),
    ...(cap === undefined ? { dailyCap: "Nhập số từ 0 đến 1000, hoặc để trống." } : {}),
    ...(min === undefined ? { gapMin: "Nhập số giây từ 0 đến 3600, hoặc để trống." } : {}),
    ...(max === undefined ? { gapMax: "Nhập số giây từ 0 đến 3600, hoặc để trống." } : {}),
    ...(gapsOrdered
      ? { gapMin: "Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa." }
      : {}),
  };
}

export function updateBody(form: IdentityForm): Schemas["IdentityUpdate"] {
  return {
    label: form.label.trim(),
    purpose: form.purpose,
    daily_cap: parseLimit(form.dailyCap, DAILY_CAP_MAX) ?? null,
    send_gap_min_s: parseLimit(form.gapMin, GAP_MAX_S) ?? null,
    send_gap_max_s: parseLimit(form.gapMax, GAP_MAX_S) ?? null,
  };
}

export function ackTimeoutText(seconds: number): string {
  return seconds % 60 === 0 ? `${seconds / 60} phút` : `${seconds} giây`;
}

/** The facts under "Tài khoản thông báo nội bộ". */
export function notifierFacts(
  internal: Pick<Identity, "label">,
  settings: Settings,
): [string, string][] {
  return [
    ["Tài khoản", internal.label],
    ["Chuông Zalo cho nhân viên", settings.bell_enabled ? "Bật" : "Tắt"],
    ["Nhóm Zalo của đội", settings.team_group_id ? "Đã đặt" : "Chưa đặt"],
    ["Chờ xác nhận trước khi gọi qua Zalo", ackTimeoutText(settings.ack_timeout_s)],
  ];
}
