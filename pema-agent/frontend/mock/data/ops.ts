// Fictional state of the shared inbox (package O): who holds a conversation and its history, the roster that
// says who covers which identity, and the notification settings of the clinic and of each operator. Synthetic
// names only (the staff of mock/auth.ts); no token, code or credential beyond a made-up one-time code.
import { USERS } from "../auth";
import { DAY, HOUR, MIN, fail, isoFromNow, uid, uuid, type Schemas } from "../core";
import { conversations } from "./clinic";

type S = Schemas;

const MAI_ANH = uuid(4, 1);
const THU = uuid(6, 1);
const DOCTOR_TAM = uuid(3, 1);

// ------------------------------------------------------------------ holder and history

const history = new Map<string, S["AssignmentEventOut"][]>();

const nameOf = (userId: string | null | undefined): string | null =>
  userId ? (USERS.find((u) => u.id === userId)?.display_name ?? null) : null;

export function userName(userId: string | null | undefined): string {
  return nameOf(userId) ?? "Đồng nghiệp";
}

/** Everything the screens show about who holds `conv`, kept in step with `assigned_user_id`. */
export function syncHolder(conv: S["ConversationOut"]): void {
  conv.assigned_user_name = nameOf(conv.assigned_user_id);
}

export function recordAssignment(
  conv: S["ConversationOut"],
  kind: S["AssignmentKind"],
  by: string | null,
  userId: string | null,
  previousId: string | null,
  reason: string | null = null,
): void {
  const list = history.get(conv.id) ?? [];
  list.unshift({
    id: uid("asg"),
    at: isoFromNow(0),
    by: by ? userName(by) : "Hệ thống",
    kind,
    previous_user_id: previousId,
    previous_user_name: nameOf(previousId),
    reason,
    user_id: userId,
    user_name: nameOf(userId),
  });
  history.set(conv.id, list);
}

/** Change the holder: one place for the version bump and the history row. */
export function setHolder(
  conv: S["ConversationOut"],
  kind: S["AssignmentKind"],
  by: string | null,
  userId: string | null,
  reason: string | null = null,
): void {
  const previous = conv.assigned_user_id ?? null;
  conv.assigned_user_id = userId;
  syncHolder(conv);
  conv.assignment_version += 1;
  conv.version += 1;
  recordAssignment(conv, kind, by, userId, previous, reason);
}

export function historyOf(conversationId: string): S["AssignmentEventOut"][] {
  return history.get(conversationId) ?? [];
}

/** 409 `thread_locked` with the holder's name, as the real action words it. */
export function lockedError(conv: S["ConversationOut"]): never {
  fail(409, "thread_locked", `${userName(conv.assigned_user_id)} đang trả lời — Tiếp quản?`);
}

// Seed: the holder of each conversation and one past hand-over, so the history dialog has rows.
const held = conversations.find((c) => c.assigned_user_id === THU);
if (held) {
  recordAssignment(held, "claim", MAI_ANH, MAI_ANH, null);
  recordAssignment(
    held,
    "takeover",
    THU,
    THU,
    MAI_ANH,
    "Chị khách cần xử lý ngay, Mai Anh đang bận ca.",
  );
}
const mine = conversations.find((c) => c.assigned_user_id === MAI_ANH);
if (mine) {
  recordAssignment(mine, "shift_end", null, null, THU);
  recordAssignment(mine, "claim", MAI_ANH, MAI_ANH, null);
}

// ------------------------------------------------------------------ identities and roster

export const identityPurpose = new Map<string, S["IdentityPurpose"]>([
  ["pema-bot", "customer"],
  ["le-tan-ca-nhan", "customer"],
  ["noi-bo", "internal"],
]);

export const identityOverrides = new Map<string, S["LimitOverrides"]>([
  ["pema-bot", { daily_cap: 10, send_gap_min_s: 20, send_gap_max_s: 45 }],
]);

const WEEKDAYS: S["Weekday"][] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEK_DAYS = WEEKDAYS.slice(0, 5);

function entry(
  n: number,
  account: string,
  user: string,
  weekdays: S["Weekday"][] | null,
  start: string,
  end: string,
): S["RosterEntryOut"] {
  const found = USERS.find((u) => u.id === user);
  return {
    id: uuid(n, 21),
    account_id: account,
    user_id: user,
    user_name: found?.display_name ?? "Nhân viên",
    user_role: found?.role ?? "cs_staff",
    weekdays,
    on_date: null,
    start,
    end,
    note: null,
    version: 1,
  };
}

export const roster: S["RosterEntryOut"][] = [
  entry(1, "le-tan-ca-nhan", MAI_ANH, WEEK_DAYS, "08:00", "12:00"),
  entry(2, "le-tan-ca-nhan", THU, WEEK_DAYS, "12:00", "17:00"),
  entry(3, "le-tan-ca-nhan", DOCTOR_TAM, ["sat"], "08:00", "12:00"),
  entry(4, "pema-bot", THU, [...WEEK_DAYS, "sat"], "08:00", "17:00"),
];

const toMinutes = (hhmm: string): number => {
  const [h, m] = hhmm.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
};

/** Day of week (0 = Monday) and minutes of the day of `at` in the clinic zone (+07:00). */
function clinicClock(at: Date): { weekday: number; minutes: number; date: string } {
  const shifted = new Date(at.getTime() + 7 * HOUR);
  return {
    weekday: (shifted.getUTCDay() + 6) % 7,
    minutes: shifted.getUTCHours() * 60 + shifted.getUTCMinutes(),
    date: shifted.toISOString().slice(0, 10),
  };
}

function covers(e: S["RosterEntryOut"], at: Date): boolean {
  const now = clinicClock(at);
  const start = toMinutes(e.start);
  const end = toMinutes(e.end);
  const overnight = end <= start;
  const dayMatches = (weekday: number, date: string): boolean =>
    e.on_date !== null
      ? e.on_date === date
      : (e.weekdays ?? []).includes(WEEKDAYS[weekday] as S["Weekday"]);
  if (!overnight)
    return dayMatches(now.weekday, now.date) && now.minutes >= start && now.minutes < end;
  const yesterday = new Date(at.getTime() - DAY);
  const before = clinicClock(yesterday);
  const today = dayMatches(now.weekday, now.date) && now.minutes >= start;
  return today || (dayMatches(before.weekday, before.date) && now.minutes < end);
}

export function onDuty(accountId: string, at: Date): S["OnDutyOperator"][] {
  const seen = new Set<string>();
  return roster
    .filter((e) => e.account_id === accountId && covers(e, at))
    .filter((e) => !seen.has(e.user_id) && seen.add(e.user_id))
    .map((e) => ({ id: e.user_id, name: e.user_name, role: e.user_role }));
}

// ------------------------------------------------------------------ notifications

export const notifySettings: S["NotifySettingsOut"] = {
  ack_timeout_s: 180,
  bell_enabled: true,
  group_enabled: true,
  in_app_enabled: true,
  public_base_url: "https://pema.example.test",
  push_enabled: false,
  team_group_id: "g-demo-001",
};

/** Per operator: linked Zalo, quiet hours, a pending one-time code. */
export type OperatorNotify = {
  linkedAt: string | null;
  quietStart: string | null;
  quietEnd: string | null;
  code: { value: string; expiresAt: number } | null;
};

const operators = new Map<string, OperatorNotify>();

export function notifyOf(userId: string): OperatorNotify {
  const found = operators.get(userId) ?? {
    linkedAt: null,
    quietStart: "22:00",
    quietEnd: "06:00",
    code: null,
  };
  operators.set(userId, found);
  return found;
}

export const CODE_TTL_MS = 10 * MIN;

export const pushTokens = new Map<
  string,
  { id: string; platform: S["PushPlatform"]; last_seen: string }[]
>();
