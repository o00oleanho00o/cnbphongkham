// Entry of the mock backend: `pnpm mock` (port 4010, override with MOCK_PORT) and
// `PEMA_API_URL=http://127.0.0.1:4010 pnpm dev`, or `pnpm dev:mock` for both.
//
// Handlers live in mock/handlers/*.ts, one file per area, each exporting `register(router)`. They are
// loaded by directory listing, so adding an area never touches this file.
import { readdirSync } from "node:fs";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";

import { register as registerAuth, sessionFromRequest } from "./auth";
import { HttpError, Router, errorBody, parseJson, readBody, type Ctx, type Reply } from "./core";

export async function buildRouter(): Promise<Router> {
  const router = new Router();
  registerAuth(router);
  const dir = fileURLToPath(new URL("./handlers/", import.meta.url));
  for (const file of readdirSync(dir).filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts"))) {
    const mod = (await import(/* @vite-ignore */ `./handlers/${file}`)) as { register?: (r: Router) => void };
    mod.register?.(router);
  }
  return router;
}

export async function startMockServer(port: number) {
  const router = await buildRouter();

  const server = createServer((req, res) => {
    void (async () => {
      const url = new URL(req.url ?? "/", "http://mock");
      const send = (reply: Reply) => {
        const status = reply.status ?? 200;
        const headers: Record<string, string> = { ...reply.headers };
        if (reply.body === undefined || status === 204) {
          res.writeHead(status, headers);
          res.end();
          return;
        }
        headers["content-type"] = "application/json; charset=utf-8";
        res.writeHead(status, headers);
        res.end(JSON.stringify(reply.body));
      };

      try {
        const found = router.match(req.method ?? "GET", url.pathname);
        if (!found) {
          send({ status: 404, body: errorBody("not_found", "Không tìm thấy đường dẫn này.") });
          return;
        }
        const raw = await readBody(req);
        const contentType = req.headers["content-type"] ?? "";
        const ctx: Ctx = {
          req,
          res,
          params: found.params,
          query: url.searchParams,
          session: sessionFromRequest(req.headers.cookie),
          body: contentType.includes("application/json") ? parseJson(raw) : {},
          raw,
        };
        const needs = found.route.permission;
        if (needs) {
          if (!ctx.session) {
            send({ status: 401, body: errorBody("unauthenticated", "Bạn chưa đăng nhập.") });
            return;
          }
          if (!ctx.session.permissions.includes(needs)) {
            send({
              status: 403,
              body: errorBody("forbidden", "Vai trò của bạn không được phép thực hiện việc này."),
            });
            return;
          }
        }
        send(await found.route.handler(ctx));
      } catch (e) {
        if (e instanceof HttpError) {
          send({ status: e.status, body: errorBody(e.code, e.message) });
          return;
        }
        send({ status: 500, body: errorBody("internal", "Lỗi máy chủ giả lập.") });
      }
    })();
  });

  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return server;
}
