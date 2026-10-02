// Mock of the three routes for several people working at once (agreed contract; not in openapi.json yet, so
// mock/contract.test.ts lists them as pending):
//   GET  /api/v1/events                           SSE, `data: {"type": "...", "id": "..."}`; no message text
//   POST /api/v1/conversations/{id}/presence      {state: "viewing" | "replying"} -> 204
//   GET  /api/v1/staff/assignable                 [{id, name, role}] for EVERY signed-in staff member
import { USERS } from "../auth";
import { fail, type Ctx, type Reply, type Router, type Session } from "../core";
import { emitLive, subscribe, touchPresence, type PresenceState } from "../live-bus";

const HEARTBEAT_MS = 15_000;

function session(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

function isState(value: unknown): value is PresenceState {
  return value === "viewing" || value === "replying";
}

export function register(r: Router): void {
  r.get("/api/v1/events", null, (ctx): Reply => {
    session(ctx);
    return {
      sse: (write) => {
        const stop = subscribe((message) => write(JSON.stringify(message)));
        const heartbeat = setInterval(() => write(null), HEARTBEAT_MS);
        return () => {
          clearInterval(heartbeat);
          stop();
        };
      },
    };
  });

  r.post("/api/v1/conversations/{conversation_id}/presence", "conversation.read", (ctx): Reply => {
    const s = session(ctx);
    const { state } = ctx.body as { state?: unknown };
    if (!isState(state))
      fail(422, "validation_failed", "Trạng thái phải là viewing hoặc replying.");
    const conversationId = ctx.params.conversation_id ?? "";
    if (touchPresence(conversationId, s.userId, state))
      emitLive("presence.changed", conversationId);
    return { status: 204 };
  });

  r.get("/api/v1/staff/assignable", null, (ctx): Reply => {
    session(ctx);
    const staff = USERS.filter((u) => u.active).map((u) => ({
      id: u.id,
      name: u.display_name,
      role: u.role,
    }));
    return { body: staff };
  });
}
