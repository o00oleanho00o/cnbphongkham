/**
 * Routes of the account lifecycle, the QR login and the kill switch.
 *
 * New module (no TS original). Replaces the in-process calls of the original (`attachAccount`,
 * `stopAccount`, `startQrLogin`, `getQrLoginStatus`) with the HTTP surface the Python API drives.
 */
import { Hono } from "hono";
import type { AppDeps } from "./deps.js";
import {
  fail,
  failFromThrown,
  ok,
  parseJsonBody,
  type AppEnv,
} from "./http.js";
import { createLogger, errorInfo } from "./logger.js";
import { accountIdSchema, killSwitchSchema, qrBodySchema, startBodySchema } from "./schemas.js";

const log = createLogger("routes-accounts");

export function accountRoutes(deps: AppDeps): Hono<AppEnv> {
  const { accounts, qr, killSwitch } = deps;
  const app = new Hono<AppEnv>();

  const idOf = (raw: string | undefined): string | null => {
    const parsed = accountIdSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  };
  const badId = (): Response => fail("bad_request", "invalid account id");

  app.get("/accounts", () => ok({ accounts: accounts.list() }));

  // Registered before `/accounts/:id/...`; the segment counts differ, so there is no clash.
  app.post("/accounts/stop-all", async () => {
    await accounts.stopAll();
    return ok({ accounts: accounts.list() });
  });

  app.get("/accounts/:id/state", (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    return ok({ state: accounts.get(id)?.state ?? "stopped" });
  });

  app.post("/accounts/:id/start", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, startBodySchema);
    if (!body.ok) return body.response;
    const { clinic_slug, credential, kill_switch } = body.data;

    // The API passes its kill switch on every start; apply it first so it holds even if the login fails.
    if (kill_switch) killSwitch.set(kill_switch);
    try {
      const { ownId } = await accounts.start(id, clinic_slug, credential);
      return ok({ own_id: ownId });
    } catch (err) {
      log.warn({ accountId: id, ...errorInfo(err) }, "start failed");
      return failFromThrown(err);
    }
  });

  app.post("/accounts/:id/stop", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    await accounts.stop(id);
    return ok({ state: accounts.get(id)?.state ?? "stopped" });
  });

  app.post("/accounts/:id/login/qr", async (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    const body = parseJsonBody(c, qrBodySchema);
    if (!body.ok) return body.response;
    const session = qr.startQrLogin(id, body.data.clinic_slug);
    return ok({ state: session.status });
  });

  app.get("/accounts/:id/login/qr", (c) => {
    const id = idOf(c.req.param("id"));
    if (!id) return badId();
    return ok({ ...qr.getQrLoginStatus(id) });
  });

  app.post("/kill-switch", async (c) => {
    const body = parseJsonBody(c, killSwitchSchema);
    if (!body.ok) return body.response;
    const state = killSwitch.set(body.data);
    log.warn({ on: state.on, scope: state.scope }, "Kill switch changed");
    return ok({ ...state });
  });

  app.get("/kill-switch", () => ok({ ...killSwitch.get() }));

  return app;
}
