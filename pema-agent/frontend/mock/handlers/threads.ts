// Mock of the agent-side conversation store: threads (sessions), contacts, memory facts. This is the LLM
// context store (`agent.history`), distinct from the clinic Inbox. Fictional text only.
import { accounts } from "./accounts";
import {
  bodyOf,
  fail,
  isoFromNow,
  paginate,
  DAY,
  HOUR,
  MIN,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const threads: S["ThreadRow"][] = [
  {
    account_id: "pema-bot",
    thread_id: "u-demo-001",
    thread_type: 0,
    display_name: "Nguyễn Thu Hà",
    bot_enabled: true,
    message_count: 18,
    last_message_at: isoFromNow(-12 * MIN),
    last_sender_name: "Nguyễn Thu Hà",
  },
  {
    account_id: "pema-bot",
    thread_id: "u-demo-002",
    thread_type: 0,
    display_name: "Trần Minh Anh",
    bot_enabled: false,
    message_count: 7,
    last_message_at: isoFromNow(-25 * MIN),
    last_sender_name: "Trần Minh Anh",
  },
  {
    account_id: "pema-bot",
    thread_id: "u-demo-004",
    thread_type: 0,
    display_name: "Khách chưa gắn hồ sơ",
    bot_enabled: true,
    message_count: 2,
    last_message_at: isoFromNow(-2 * HOUR),
    last_sender_name: null,
  },
  {
    account_id: "le-tan-ca-nhan",
    thread_id: "u-demo-021",
    thread_type: 0,
    display_name: "Lễ tân Trâm",
    bot_enabled: true,
    message_count: 64,
    last_message_at: isoFromNow(-3 * HOUR),
    last_sender_name: "Lễ tân Trâm",
  },
  {
    account_id: "le-tan-ca-nhan",
    thread_id: "g-demo-001",
    thread_type: 1,
    display_name: "Nhóm điều phối phòng khám",
    bot_enabled: true,
    message_count: 240,
    last_message_at: isoFromNow(-1 * DAY),
    last_sender_name: "Mai Anh",
  },
];

const messages = new Map<string, S["StoredMessage"][]>([
  [
    "pema-bot:u-demo-001",
    [
      {
        id: 1,
        role: "user",
        content: "Chào phòng khám, em là Hà, hôm qua em làm laser.",
        sender_id: "u-demo-001",
        sender_name: "Nguyễn Thu Hà",
        created_at: isoFromNow(-3 * DAY),
        images: [],
      },
      {
        id: 2,
        role: "assistant",
        content:
          "Chào chị, em là trợ lý của phòng khám. Chị cần hỗ trợ gì về chăm sóc da sau laser ạ?",
        sender_id: null,
        sender_name: null,
        created_at: isoFromNow(-3 * DAY + MIN),
        images: [],
      },
      {
        id: 3,
        role: "user",
        content: "Da em hơi đỏ, em chụp gửi ạ.",
        sender_id: "u-demo-001",
        sender_name: "Nguyễn Thu Hà",
        created_at: isoFromNow(-12 * MIN),
        images: ["media-demo-1"],
      },
    ],
  ],
]);

const contacts: S["ContactRow"][] = threads.map((t, i) => ({
  account_id: t.account_id,
  user_id: t.thread_id,
  display_name: t.display_name,
  first_seen: isoFromNow(-(30 + i) * DAY),
  last_seen: t.last_message_at ?? isoFromNow(-1 * DAY),
  message_count: t.message_count,
}));

const facts: S["MemoryFact"][] = [
  {
    id: 1,
    account_id: "le-tan-ca-nhan",
    subject_id: "u-demo-021",
    content: "Thích được nhắc lịch trước một ngày bằng tin nhắn ngắn.",
    learned_in_thread_id: "u-demo-021",
    learned_in_group: false,
    created_at: isoFromNow(-9 * DAY),
  },
  {
    id: 2,
    account_id: "le-tan-ca-nhan",
    subject_id: "g-demo-001",
    content: "Nhóm điều phối họp giao ban lúc 8 giờ sáng thứ Hai.",
    learned_in_thread_id: "g-demo-001",
    learned_in_group: true,
    created_at: isoFromNow(-20 * DAY),
  },
];

function threadOr404(ctxParams: Record<string, string>): S["ThreadRow"] {
  const found = threads.find(
    (t) => t.account_id === ctxParams.account_id && t.thread_id === ctxParams.thread_id,
  );
  if (!found) fail(404, "not_found", "Không tìm thấy cuộc trò chuyện.");
  return found;
}

function matches(text: string, q: string | null): boolean {
  return !q || text.toLowerCase().includes(q.toLowerCase());
}

export function register(r: Router): void {
  r.get("/api/v1/admin/threads", "admin.agents", (ctx): Reply => {
    const account = ctx.query.get("account_id");
    const q = ctx.query.get("q");
    const found = threads
      .filter((t) => !account || t.account_id === account)
      .filter((t) => matches(`${t.display_name} ${t.thread_id}`, q))
      .toSorted((a, b) => (b.last_message_at ?? "").localeCompare(a.last_message_at ?? ""));
    return { body: paginate(found, ctx.query).items };
  });

  r.patch("/api/v1/admin/threads/{account_id}/{thread_id}", "admin.agents", (ctx): Reply => {
    const thread = threadOr404(ctx.params);
    const input = bodyOf<S["ThreadUpdate"]>(ctx);
    if (input.bot_enabled !== undefined && input.bot_enabled !== null)
      thread.bot_enabled = input.bot_enabled;
    if (input.display_name) thread.display_name = input.display_name;
    return { body: thread };
  });

  r.delete("/api/v1/admin/threads/{account_id}/{thread_id}", "admin.agents", (ctx): Reply => {
    const thread = threadOr404(ctx.params);
    threads.splice(threads.indexOf(thread), 1);
    messages.delete(`${thread.account_id}:${thread.thread_id}`);
    return { status: 204 };
  });

  r.delete(
    "/api/v1/admin/threads/{account_id}/{thread_id}/history",
    "admin.agents",
    (ctx): Reply => {
      const thread = threadOr404(ctx.params);
      messages.delete(`${thread.account_id}:${thread.thread_id}`);
      thread.message_count = 0;
      return { status: 204 };
    },
  );

  r.delete(
    "/api/v1/admin/threads/{account_id}/{thread_id}/summary",
    "admin.agents",
    (ctx): Reply => {
      threadOr404(ctx.params);
      return { status: 204 };
    },
  );

  r.get("/api/v1/admin/threads/{account_id}/{thread_id}/messages", "admin.agents", (ctx): Reply => {
    const thread = threadOr404(ctx.params);
    const all = messages.get(`${thread.account_id}:${thread.thread_id}`) ?? [];
    const before = Number.parseInt(ctx.query.get("before_id") ?? "", 10);
    const limit = Number.parseInt(ctx.query.get("limit") ?? "50", 10) || 50;
    const older = Number.isNaN(before) ? all : all.filter((m) => (m.id ?? 0) < before);
    return { body: older.slice(-limit) };
  });

  r.get("/api/v1/admin/contacts", "admin.agents", (ctx): Reply => {
    const account = ctx.query.get("account_id");
    const q = ctx.query.get("q");
    const found = contacts
      .filter((c) => !account || c.account_id === account)
      .filter((c) => matches(`${c.display_name} ${c.user_id}`, q));
    return { body: paginate(found, ctx.query).items };
  });

  r.delete("/api/v1/admin/contacts/{account_id}/{user_id}", "admin.agents", (ctx): Reply => {
    const index = contacts.findIndex(
      (c) => c.account_id === ctx.params.account_id && c.user_id === ctx.params.user_id,
    );
    if (index < 0) fail(404, "not_found", "Không tìm thấy liên hệ.");
    contacts.splice(index, 1);
    return { status: 204 };
  });

  r.get("/api/v1/admin/memories", "admin.agents", (ctx): Reply => {
    const account = ctx.query.get("account_id");
    const q = ctx.query.get("q");
    const found = facts
      .filter((f) => !account || f.account_id === account)
      .filter((f) => accounts.some((a) => a.id === f.account_id))
      .filter((f) => matches(`${f.content} ${f.subject_id}`, q));
    return { body: paginate(found, ctx.query).items };
  });

  r.delete("/api/v1/admin/memories/{account_id}/{fact_id}", "admin.agents", (ctx): Reply => {
    const index = facts.findIndex(
      (f) => f.account_id === ctx.params.account_id && String(f.id) === ctx.params.fact_id,
    );
    if (index < 0) fail(404, "not_found", "Không tìm thấy mục ghi nhớ.");
    facts.splice(index, 1);
    return { status: 204 };
  });
}
