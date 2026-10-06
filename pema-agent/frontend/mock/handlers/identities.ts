// Mock of the clinic identities and the roster (package O, step O1):
//   GET   /identities, PATCH /identities/{id}      purpose, label and send limits; never a credential
//   GET   /identities/{id}/on-duty                 who covers an identity at a moment
//   GET/POST /roster, PATCH/DELETE /roster/{id}    who covers which identity, when
import { USERS } from "../auth";
import { assertAssignable } from "../assignable";
import { conversations } from "../data/clinic";
import { identityOverrides, identityPurpose, onDuty, roster } from "../data/ops";
import { accounts, channels } from "./accounts";
import { bodyOf, fail, uuid, type Ctx, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

const TIME = /^([01]\d|2[0-3]):[0-5]\d$/;
const NOTE_MAX = 200;
const LIMIT_MAX = 3600;

function identityOut(account: S["AccountOut"]): S["IdentityOut"] {
  const channel = channels.find((c) => c.channel === account.channel);
  const overrides = identityOverrides.get(account.id) ?? {};
  return {
    id: account.id,
    label: account.label,
    channel: account.channel,
    purpose: identityPurpose.get(account.id) ?? "customer",
    enabled: account.enabled,
    channel_enabled: channel?.enabled ?? false,
    kill_switch_on: channel?.kill_switch_on ?? false,
    bridge_state: channel?.bridge_state ?? null,
    overrides: { daily_cap: null, send_gap_min_s: null, send_gap_max_s: null, ...overrides },
    effective: {
      daily_cap: overrides.daily_cap ?? channel?.daily_cap ?? null,
      send_gap_min_s: overrides.send_gap_min_s ?? channel?.min_gap_seconds ?? 0,
      send_gap_max_s: overrides.send_gap_max_s ?? channel?.max_gap_seconds ?? 0,
    },
  };
}

function accountOr404(id: string): S["AccountOut"] {
  const found = accounts.find((a) => a.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy danh tính.");
  return found;
}

function validGap(value: number | null | undefined): boolean {
  return (
    value === null ||
    value === undefined ||
    (Number.isInteger(value) && value >= 0 && value <= LIMIT_MAX)
  );
}

function updateIdentity(ctx: Ctx): Reply {
  const account = accountOr404(ctx.params.account_id ?? "");
  const body = bodyOf<S["IdentityUpdate"]>(ctx);
  const sent = new Set(Object.keys(body));
  const current = identityOverrides.get(account.id) ?? {};
  const next = {
    daily_cap: sent.has("daily_cap") ? body.daily_cap : current.daily_cap,
    send_gap_min_s: sent.has("send_gap_min_s") ? body.send_gap_min_s : current.send_gap_min_s,
    send_gap_max_s: sent.has("send_gap_max_s") ? body.send_gap_max_s : current.send_gap_max_s,
  };
  if (!validGap(next.send_gap_min_s) || !validGap(next.send_gap_max_s)) {
    fail(422, "validation_failed", "Khoảng nghỉ phải từ 0 đến 3600 giây.");
  }
  const min = next.send_gap_min_s ?? 0;
  const max = next.send_gap_max_s ?? LIMIT_MAX;
  if (min > max) {
    fail(422, "validation_failed", "Khoảng nghỉ tối thiểu không được lớn hơn khoảng nghỉ tối đa.");
  }
  if (body.label !== undefined && body.label !== null && !body.label.trim()) {
    fail(422, "validation_failed", "Tên danh tính không được để trống.");
  }
  const purpose = body.purpose ?? identityPurpose.get(account.id) ?? "customer";
  const busy =
    (account.channel === "zalo_bot" && conversations.some((c) => c.status !== "closed")) ||
    roster.some((e) => e.account_id === account.id);
  if (purpose === "internal" && identityPurpose.get(account.id) !== "internal" && busy) {
    fail(409, "invalid_state", "Không đổi được: còn hội thoại đang gắn với danh tính này.");
  }
  identityPurpose.set(account.id, purpose);
  identityOverrides.set(account.id, {
    daily_cap: next.daily_cap ?? null,
    send_gap_min_s: next.send_gap_min_s ?? null,
    send_gap_max_s: next.send_gap_max_s ?? null,
  });
  if (body.label?.trim()) account.label = body.label.trim();
  return { body: identityOut(account) };
}

function checkEntry(input: {
  account_id?: string | null;
  user_id?: string | null;
  start?: string | null;
  end?: string | null;
  note?: string | null;
  weekdays?: S["Weekday"][] | null;
  on_date?: string | null;
}): void {
  if (input.account_id) accountOr404(input.account_id);
  if (input.user_id) assertAssignable(input.user_id);
  if (input.start && !TIME.test(input.start))
    fail(422, "validation_failed", "Giờ bắt đầu không hợp lệ.");
  if (input.end && !TIME.test(input.end))
    fail(422, "validation_failed", "Giờ kết thúc không hợp lệ.");
  if (input.start && input.start === input.end) {
    fail(422, "validation_failed", "Giờ bắt đầu và giờ kết thúc phải khác nhau.");
  }
  if (input.note && input.note.length > NOTE_MAX) {
    fail(422, "validation_failed", "Ghi chú tối đa 200 ký tự.");
  }
  const recurring = (input.weekdays?.length ?? 0) > 0;
  if (recurring === Boolean(input.on_date)) {
    fail(422, "validation_failed", "Chọn lặp theo thứ hoặc một ngày, không chọn cả hai.");
  }
}

function entryOr404(ctx: Ctx): S["RosterEntryOut"] {
  const found = roster.find((e) => e.id === ctx.params.entry_id);
  if (!found) fail(404, "not_found", "Không tìm thấy ca trực.");
  return found;
}

export function register(r: Router): void {
  r.get("/api/v1/identities", null, (ctx): Reply => {
    if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
    const ordered = accounts.toSorted(
      (a, b) =>
        Number(identityPurpose.get(a.id) === "internal") -
        Number(identityPurpose.get(b.id) === "internal"),
    );
    return { body: ordered.map(identityOut) };
  });

  r.patch("/api/v1/identities/{account_id}", "identity.manage", updateIdentity);

  r.get("/api/v1/identities/{account_id}/on-duty", null, (ctx): Reply => {
    if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
    const account = accountOr404(ctx.params.account_id ?? "");
    const at = ctx.query.get("at");
    const moment = at ? new Date(at) : new Date();
    const body: S["OnDutyOut"] = {
      account_id: account.id,
      at: moment.toISOString(),
      operators: onDuty(account.id, moment),
    };
    return { body };
  });

  r.get("/api/v1/roster", "roster.read", (ctx): Reply => {
    const account = ctx.query.get("account_id");
    const user = ctx.query.get("user_id");
    return {
      body: roster.filter(
        (e) => (!account || e.account_id === account) && (!user || e.user_id === user),
      ),
    };
  });

  r.post("/api/v1/roster", "roster.manage", (ctx): Reply => {
    const input = bodyOf<S["RosterEntryCreate"]>(ctx);
    checkEntry(input);
    const who = USERS.find((u) => u.id === input.user_id);
    const created: S["RosterEntryOut"] = {
      id: uuid(100 + roster.length, 21),
      account_id: input.account_id,
      user_id: input.user_id,
      user_name: who?.display_name ?? "Nhân viên",
      user_role: who?.role ?? "cs_staff",
      weekdays: input.weekdays ?? null,
      on_date: input.on_date ?? null,
      start: input.start,
      end: input.end,
      note: input.note?.trim() || null,
      version: 1,
    };
    roster.push(created);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/roster/{entry_id}", "roster.manage", (ctx): Reply => {
    const found = entryOr404(ctx);
    const input = bodyOf<S["RosterEntryUpdate"]>(ctx);
    if (input.version !== found.version) {
      fail(409, "version_conflict", "Ca trực vừa được người khác sửa. Đã tải lại.");
    }
    const merged = {
      user_id: input.user_id ?? found.user_id,
      start: input.start ?? found.start,
      end: input.end ?? found.end,
      note: input.note === undefined ? found.note : input.note,
      weekdays: input.on_date ? null : (input.weekdays ?? found.weekdays),
      on_date: input.weekdays?.length ? null : (input.on_date ?? found.on_date),
    };
    checkEntry(merged);
    const who = USERS.find((u) => u.id === merged.user_id);
    Object.assign(found, merged, {
      note: merged.note?.trim() || null,
      user_name: who?.display_name ?? found.user_name,
      user_role: who?.role ?? found.user_role,
      version: found.version + 1,
    });
    return { body: found };
  });

  r.delete("/api/v1/roster/{entry_id}", "roster.manage", (ctx): Reply => {
    const found = entryOr404(ctx);
    roster.splice(roster.indexOf(found), 1);
    return { status: 204 };
  });
}
