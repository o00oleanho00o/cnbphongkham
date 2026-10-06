// Mock of who holds a conversation (package O, step O2). The BE decides every rule; this only reproduces its
// answers so the screens can be built:
//   POST /conversations/{id}/claim      nobody holds it -> me; a colleague holds it -> 409 thread_locked
//   POST /conversations/{id}/takeover   {reason} a colleague holds it -> me
//   POST /conversations/{id}/release    {to_agent, note} the holder (or an owner/manager) gives it back
//   POST /conversations/{id}/assign     {user_id | null} owner and manager
//   GET  /conversations/{id}/assignments  history, newest first
//   POST /staff/{user_id}/end-shift     the open threads of that person move on
import { assertAssignable } from "../assignable";
import { conversations } from "../data/clinic";
import { historyOf, onDuty, setHolder, lockedError } from "../data/ops";
import {
  bodyOf,
  fail,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
  type Session,
} from "../core";

type S = Schemas;

function session(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

function conversationOf(ctx: Ctx): S["ConversationOut"] {
  const id = ctx.params.conversation_id ?? "";
  const found = conversations.find((c) => c.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy hội thoại.");
  return found;
}

const REASON_MAX = 500;

export function register(r: Router): void {
  r.post("/api/v1/conversations/{conversation_id}/claim", "thread.claim", (ctx): Reply => {
    const me = session(ctx).userId;
    const conv = conversationOf(ctx);
    if (conv.assigned_user_id === me) return { body: conv };
    if (conv.assigned_user_id) lockedError(conv);
    setHolder(conv, "claim", me, me);
    return { body: conv };
  });

  r.post("/api/v1/conversations/{conversation_id}/takeover", "thread.claim", (ctx): Reply => {
    const me = session(ctx).userId;
    const conv = conversationOf(ctx);
    const { reason } = bodyOf<S["TakeoverRequest"]>(ctx);
    if (!reason?.trim() || reason.length > REASON_MAX) {
      fail(422, "validation_failed", "Hãy nhập lý do tiếp quản (tối đa 500 ký tự).");
    }
    if (!conv.assigned_user_id)
      fail(409, "invalid_state", "Hội thoại chưa có người phụ trách: bấm Nhận.");
    if (conv.assigned_user_id === me)
      fail(409, "invalid_state", "Bạn đang phụ trách hội thoại này.");
    setHolder(conv, "takeover", me, me, reason.trim());
    return { body: conv };
  });

  r.post("/api/v1/conversations/{conversation_id}/release", "thread.claim", (ctx): Reply => {
    const user = session(ctx);
    const conv = conversationOf(ctx);
    const { to_agent: toAgent, note } = bodyOf<S["ReleaseRequest"]>(ctx);
    if (!conv.assigned_user_id) fail(409, "invalid_state", "Hội thoại chưa có người phụ trách.");
    const mayRelease =
      conv.assigned_user_id === user.userId || user.permissions.includes("thread.assign");
    if (!mayRelease) fail(403, "forbidden", "Chỉ người đang phụ trách mới trả lại được.");
    if (toAgent)
      fail(
        501,
        "not_implemented",
        "Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được.",
      );
    if (note && note.length > REASON_MAX)
      fail(422, "validation_failed", "Ghi chú tối đa 500 ký tự.");
    setHolder(conv, "release", user.userId, null, note?.trim() || null);
    return { body: conv };
  });

  r.post("/api/v1/conversations/{conversation_id}/assign", "thread.assign", (ctx): Reply => {
    const user = session(ctx);
    const conv = conversationOf(ctx);
    const { user_id: target } = bodyOf<S["AssignRequest"]>(ctx);
    if (target) assertAssignable(target);
    setHolder(conv, "assign", user.userId, target ?? null);
    return { body: conv };
  });

  r.get(
    "/api/v1/conversations/{conversation_id}/assignments",
    "conversation.read",
    (ctx): Reply => ({
      body: historyOf(conversationOf(ctx).id),
    }),
  );

  r.post("/api/v1/staff/{user_id}/end-shift", "thread.end_shift", (ctx): Reply => {
    const actor = session(ctx).userId;
    const userId = ctx.params.user_id ?? "";
    const open = conversations.filter(
      (c) => c.assigned_user_id === userId && c.status !== "closed",
    );
    const covering = (accountId: string): string | undefined =>
      onDuty(accountId, new Date()).find((o) => o.id !== userId)?.id;
    const moves = open.map((conv) => ({ conv, to: covering("pema-bot") ?? null }));
    moves.forEach(({ conv, to }) => setHolder(conv, "shift_end", actor, to));
    const handed = moves.filter((m) => m.to !== null).length;
    const result: S["EndShiftResult"] = {
      user_id: userId,
      rerouted: handed,
      to_queue: moves.length - handed,
      skipped: 0,
    };
    return { body: result };
  });
}
