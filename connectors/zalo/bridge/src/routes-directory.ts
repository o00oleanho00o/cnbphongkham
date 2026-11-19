// ported from: src/server/routes/friend-routes.ts (list, accept, reject). The pending-request store
// (`xoaFriendRequest`) is the Python API's: it deletes its row after the bridge answers ok.
/**
 * Read routes and friend actions: user-info, friends, accept/reject, group-info.
 *
 * `friends` returns ONLY userId/displayName/zaloName, never phone or date of birth (PII of the friends of
 * the account): see `summarizeFriends`.
 */
import { Hono } from "hono";
import type { AppDeps } from "./deps.js";
import { summarizeFriends } from "./friends.js";
import {
  fail,
  failFromThrown,
  ok,
  parseJsonBody,
  parseQuery,
  type AppContext,
  type AppEnv,
} from "./http.js";
import { createLogger, errorInfo } from "./logger.js";
import {
  accountIdSchema,
  friendActionBodySchema,
  groupInfoQuerySchema,
  userInfoQuerySchema,
} from "./schemas.js";
import type { ZaloApi } from "./zalo-types.js";

const log = createLogger("routes-directory");

export function directoryRoutes(deps: AppDeps): Hono<AppEnv> {
  const { accounts } = deps;
  const app = new Hono<AppEnv>();

  /** `null` = invalid id (400) or account not running (409), already turned into a response. */
  const resolveApi = (rawId: string | undefined): { api: ZaloApi } | { response: Response } => {
    const id = accountIdSchema.safeParse(rawId);
    if (!id.success) return { response: fail("bad_request", "invalid account id") };
    const account = accounts.get(id.data);
    if (!account?.canSend || !account.api) {
      return { response: fail("not_running", "Account is not running") };
    }
    return { api: account.api };
  };

  app.get("/accounts/:id/user-info", async (c) => {
    const resolved = resolveApi(c.req.param("id"));
    if ("response" in resolved) return resolved.response;
    const query = parseQuery(c, userInfoQuerySchema);
    if (!query.ok) return query.response;
    try {
      return ok({ data: await resolved.api.getUserInfo(query.data.uid) });
    } catch (err) {
      return failFromThrown(err);
    }
  });

  app.get("/accounts/:id/friends", async (c) => {
    const resolved = resolveApi(c.req.param("id"));
    if ("response" in resolved) return resolved.response;
    try {
      return ok({ friends: summarizeFriends(await resolved.api.getAllFriends()) });
    } catch (err) {
      log.warn(errorInfo(err), "getAllFriends lỗi");
      return failFromThrown(err);
    }
  });

  /** Chung cho accept + reject: validate body, lấy api, gọi hành động. */
  const friendAction =
    (call: (api: ZaloApi, uid: string) => Promise<unknown>) =>
    async (c: AppContext): Promise<Response> => {
      const resolved = resolveApi(c.req.param("id"));
      if ("response" in resolved) return resolved.response;
      const body = parseJsonBody(c, friendActionBodySchema);
      if (!body.ok) return body.response;
      try {
        await call(resolved.api, body.data.uid);
        return ok();
      } catch (err) {
        log.warn(errorInfo(err), "duyệt kết bạn thất bại");
        return failFromThrown(err);
      }
    };

  app.post(
    "/accounts/:id/friends/accept",
    friendAction((api, uid) => api.acceptFriendRequest(uid)),
  );
  app.post(
    "/accounts/:id/friends/reject",
    friendAction((api, uid) => api.rejectFriendRequest(uid)),
  );

  app.get("/accounts/:id/group-info", async (c) => {
    const resolved = resolveApi(c.req.param("id"));
    if ("response" in resolved) return resolved.response;
    const query = parseQuery(c, groupInfoQuerySchema);
    if (!query.ok) return query.response;
    try {
      return ok({ data: await resolved.api.getGroupInfo(query.data.thread_id) });
    } catch (err) {
      return failFromThrown(err);
    }
  });

  return app;
}
