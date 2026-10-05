// Mock of usage, traces and logs (admin.usage / admin.logs). Trace steps and log lines are fictional and
// carry no message text of a patient.
import { accounts } from "./accounts";
import { CLINIC_ID, USERS } from "../auth";
import {
  fail,
  isoFromNow,
  paginate,
  DAY,
  MIN,
  toVn,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const START = Date.now();

function dailyFor(accountId: string, days: number): S["DailyUsage"][] {
  const weight = accountId === "pema-bot" ? 1 : 0.4;
  return Array.from({ length: days }, (_, i) => {
    const offset = days - 1 - i;
    const day = toVn(new Date(Date.now() - offset * DAY)).slice(0, 10);
    const base = 18 + ((i * 7) % 13);
    const turns = Math.round(base * weight);
    return { day, turns, input_tokens: turns * 1400, output_tokens: turns * 220 };
  });
}

function overview(days: 7 | 14 | 30): S["OverviewOut"] {
  return {
    days,
    timezone: "Asia/Ho_Chi_Minh",
    today_key: toVn(new Date()).slice(0, 10),
    system: {
      python: "3.12",
      version: "mock",
      uptime_seconds: Math.floor((Date.now() - START) / 1000) + 90_000,
    },
    accounts: accounts.map((a) => ({
      id: a.id,
      label: a.label,
      enabled: a.enabled ?? true,
      online: !!a.running,
    })),
    usage_by_account: accounts.map((a) => ({ account_id: a.id, daily: dailyFor(a.id, days) })),
    stats_by_account: accounts.map((a, i) => ({
      account_id: a.id,
      threads: i === 0 ? 3 : 2,
      messages_today: i === 0 ? 41 : 12,
      turns_today: i === 0 ? 19 : 6,
      tokens_today: i === 0 ? 31_000 : 9_000,
    })),
  };
}

// ------------------------------------------------------------------ traces

type TurnSeed = S["TraceTurnRow"];

const turns: TurnSeed[] = Array.from({ length: 12 }, (_, i) => ({
  id: 60 - i,
  account_id: i % 4 === 3 ? "le-tan-ca-nhan" : "pema-bot",
  thread_id: i % 4 === 3 ? "u-demo-021" : "u-demo-001",
  thread_name: i % 4 === 3 ? "Lễ tân Trâm" : "Nguyễn Thu Hà",
  created_at: isoFromNow(-(i * 47 + 5) * MIN),
  source: i % 5 === 4 ? "schedule" : "message",
  steps: 2 + (i % 3),
  input_tokens: 1500 + i * 130,
  output_tokens: 180 + i * 12,
  total_tokens: 1680 + i * 142,
}));

function stepsFor(turnId: number): S["TraceStepRow"][] {
  const turn = turns.find((t) => t.id === turnId);
  if (!turn) fail(404, "not_found", "Không tìm thấy lượt agent.");
  return Array.from({ length: turn.steps }, (_, i) => ({
    id: turnId * 10 + i,
    turn_id: turnId,
    step_number: i + 1,
    created_at: turn.created_at,
    attempt: 1,
    finish_reason: i === turn.steps - 1 ? "stop" : "tool-calls",
    input_tokens: 700 + i * 200,
    output_tokens: 60 + i * 30,
    reasoning: "",
    text: i === turn.steps - 1 ? "Em đã soạn nháp trả lời kèm nguồn, chờ nhân viên duyệt." : "",
    warnings: [],
    tool_calls:
      i === turn.steps - 1
        ? []
        : [{ name: "kb_search", input: { query: "chăm sóc da sau laser" } }],
    tool_results:
      i === turn.steps - 1
        ? []
        : [{ name: "kb_search", output: "3 đoạn từ 2 nguồn đã được bác sĩ duyệt." }],
    tool_errors: [],
  }));
}

// -------------------------------------------------------------------- logs

const SCOPES = [
  "http",
  "channel.zalo_bot",
  "agent.loop",
  "scheduler",
  "knowledge.ingest",
  "policy",
];
const LEVELS: S["LogEntry"]["level"][] = ["info", "info", "debug", "warn", "info", "error", "info"];

const logEntries: S["LogEntry"][] = Array.from({ length: 220 }, (_, i) => ({
  time: isoFromNow(-i * 37_000),
  level: LEVELS[i % LEVELS.length] ?? "info",
  scope: SCOPES[i % SCOPES.length] ?? "http",
  message:
    [
      "Nhận tin nhắn đến, đã xếp vào hàng đợi",
      "Lượt agent hoàn tất",
      "Quét hàng đợi việc đến hạn",
      "Cờ đỏ: chuyển bác sĩ trước khi gọi mô hình",
      "Nạp tài liệu: đã cắt đoạn xong",
      "Gửi tin lỗi: kênh không khả dụng, sẽ thử lại",
      "Nháp chờ duyệt đã được tạo",
    ][i % 7] ?? "",
  fields: i % 3 === 0 ? { turn_id: 60 - (i % 12), account_id: "pema-bot" } : null,
}));

const RANK: Record<S["LogEntry"]["level"], number> = {
  trace: 10,
  debug: 20,
  info: 30,
  warn: 40,
  error: 50,
  fatal: 60,
};

const audit: S["AuditLogOut"][] = Array.from({ length: 70 }, (_, i) => {
  const user = USERS[i % USERS.length];
  const actions = [
    ["review.approve", "review_item"],
    ["auth.login", "session"],
    ["crm.task.resolve", "crm_task"],
    ["template.approve", "message_template"],
    ["channel.kill_switch", "channel_setting"],
    ["policy.account.update", "account"],
  ] as const;
  const [action, entity] = actions[i % actions.length] ?? actions[0];
  return {
    id: 1000 - i,
    occurred_at: isoFromNow(-i * 23 * MIN),
    action,
    entity_type: entity,
    entity_id: `00000000-0000-4000-8000-${String(i).padStart(12, "0")}`,
    actor_type: i % 7 === 6 ? "agent" : "user",
    actor_role: i % 7 === 6 ? null : (user?.role ?? null),
    actor_user_id: i % 7 === 6 ? null : (user?.id ?? null),
    details: { clinic_id: CLINIC_ID, via: "mock" },
    request_id: `req-${i}`,
  };
});

export function register(r: Router): void {
  r.get("/api/v1/admin/usage/overview", "admin.usage", (ctx): Reply => {
    const raw = Number.parseInt(ctx.query.get("days") ?? "7", 10);
    const days = raw === 14 || raw === 30 ? raw : 7;
    return { body: overview(days) };
  });

  r.get("/api/v1/admin/traces", "admin.usage", (ctx): Reply => {
    const before = Number.parseInt(ctx.query.get("before") ?? "", 10);
    const limit = Number.parseInt(ctx.query.get("limit") ?? "50", 10) || 50;
    const page = turns.filter((t) => Number.isNaN(before) || t.id < before);
    const slice = page.slice(0, limit);
    const last = slice.at(-1);
    return { body: { turns: slice, next_cursor: page.length > limit && last ? last.id : null } };
  });

  r.get("/api/v1/admin/traces/turn/{turn_id}", "admin.usage", (ctx): Reply => ({
    body: stepsFor(Number.parseInt(ctx.params.turn_id ?? "", 10)),
  }));

  r.get("/api/v1/admin/traces/{account_id}/{thread_id}", "admin.usage", (ctx): Reply => ({
    body: {
      turns: turns.filter(
        (t) => t.account_id === ctx.params.account_id && t.thread_id === ctx.params.thread_id,
      ),
      next_cursor: null,
    },
  }));

  r.get("/api/v1/admin/logs/app", "admin.logs", (ctx): Reply => {
    const level = ctx.query.get("level") as S["LogEntry"]["level"] | null;
    const scope = ctx.query.get("scope");
    const search = (ctx.query.get("search") ?? "").toLowerCase();
    const offset = Number.parseInt(ctx.query.get("before") ?? "0", 10) || 0;
    const limit = Number.parseInt(ctx.query.get("limit") ?? "200", 10) || 200;
    const filtered = logEntries
      .filter((e) => !level || RANK[e.level] >= RANK[level])
      .filter((e) => !scope || e.scope === scope)
      .filter((e) => !search || e.message.toLowerCase().includes(search));
    const slice = filtered.slice(offset, offset + limit);
    return {
      body: {
        entries: slice,
        scopes: SCOPES,
        next_cursor: offset + limit < filtered.length ? String(offset + limit) : null,
        disabled: false,
        hint: null,
      },
    };
  });

  r.get("/api/v1/admin/logs/audit", "admin.logs", (ctx): Reply => {
    const action = ctx.query.get("action");
    const entity = ctx.query.get("entity_type");
    const found = audit
      .filter((a) => !action || a.action.includes(action))
      .filter((a) => !entity || a.entity_type === entity);
    return { body: paginate(found, ctx.query) };
  });
}
