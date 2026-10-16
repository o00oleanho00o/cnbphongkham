// Mock of the routes for several people working at once (all in openapi.json, backend package ST-R):
//   GET    /api/v1/events                         SSE, `data: {"type": "...", "id": "..."}`; no message text
// (`GET /api/v1/staff/assignable` is in mock/handlers/staff.ts.)
import { fail, type Ctx, type Reply, type Router, type Session } from "../core";
import { subscribe } from "../live-bus";

const HEARTBEAT_MS = 15_000;

function session(ctx: Ctx): Session {
  if (!ctx.session) fail(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
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
}
