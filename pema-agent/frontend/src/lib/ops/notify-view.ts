// Words and checks for "Thông báo của tôi" (frames WM42-WM51): the one-time code that links a personal Zalo, quiet
// hours and the registered phones. Pure, so the countdown and the form rules are tested without a screen. The BE
// owns the chain (in-app, push, Zalo bell, team group) and the code (ten minutes, used once); this only shows it.
import type { Schemas } from "@/lib/api";

export type QuietForm = { enabled: boolean; start: string; end: string };

export const DEFAULT_QUIET: Pick<QuietForm, "start" | "end"> = { start: "22:00", end: "06:00" };

export function quietFormOf(pref: Schemas["NotifyPreferenceOut"]): QuietForm {
  const enabled = Boolean(pref.quiet_start && pref.quiet_end);
  return {
    enabled,
    start: pref.quiet_start ?? DEFAULT_QUIET.start,
    end: pref.quiet_end ?? DEFAULT_QUIET.end,
  };
}

/** The body of `PUT /me/notify-preferences`: both times, or both null to turn quiet hours off. */
export function quietBody(form: QuietForm): Schemas["NotifyPreferenceIn"] {
  return form.enabled
    ? { quiet_start: form.start, quiet_end: form.end }
    : { quiet_start: null, quiet_end: null };
}

export function quietError(form: QuietForm): string | null {
  if (!form.enabled) return null;
  if (form.start === "" || form.end === "") return "Chọn cả giờ bắt đầu và giờ kết thúc.";
  return form.start === form.end ? "Hai mốc giờ phải khác nhau." : null;
}

/** Seconds left on a code, never below zero. */
export function secondsLeft(expiresAtMs: number, nowMs: number): number {
  return Math.max(0, Math.ceil((expiresAtMs - nowMs) / 1000));
}

/** "09:12" for 552 seconds. */
export function countdownText(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

const PLATFORM_LABEL: Record<Schemas["PushPlatform"], string> = {
  android: "Android",
  ios: "iOS",
  web: "Trình duyệt",
};

/** "iOS · hoạt động 20/09" under a registered phone. */
export function deviceLine(
  device: Pick<Schemas["PushTokenOut"], "platform" | "last_seen">,
): string {
  const seen = new Date(device.last_seen);
  const day = Number.isNaN(seen.getTime())
    ? ""
    : new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
      }).format(seen);
  return day
    ? `${PLATFORM_LABEL[device.platform]} · hoạt động ${day}`
    : PLATFORM_LABEL[device.platform];
}

export const NO_INTERNAL_TEXT =
  "Phòng khám chưa cấu hình tài khoản thông báo nội bộ nên chưa liên kết Zalo được. Bạn vẫn nhận thông báo trong ứng dụng.";
