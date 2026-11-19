// Entry of the mock backend: `bun run mock` (port 4010, override with MOCK_PORT) and
// `PEMA_AGENT_INTERNAL_URL=http://127.0.0.1:4010 bun run dev`, or `bun run dev:mock` for both.
//
// It plays the agent service (mock/agent.ts, with the sign-in of its plugin `web`) and the Zalo connector
// (mock/connector-zalo.ts). The web's own server answers `/api/v1` (sign-in) and calls this as the agent.
import { createServer } from "node:http";

import { answerAgent, buildAgentRouter, isAgentPath } from "./agent";
import { buildZaloConnectorRouter } from "./connector-zalo";
import { HttpError, errorBody, type Reply } from "./core";

export async function startMockServer(port: number) {
  const agentRouters = { agent: buildAgentRouter(), zalo: buildZaloConnectorRouter() };

  const server = createServer((req, res) => {
    void (async () => {
      const url = new URL(req.url ?? "/", "http://mock");
      const send = (reply: Reply) => {
        const status = reply.status ?? 200;
        const headers: Record<string, string> = { ...reply.headers };
        if (reply.raw !== undefined) {
          res.writeHead(status, headers);
          res.end(reply.raw);
          return;
        }
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
        if (url.pathname === "/health") {
          send({ body: { ok: true } });
          return;
        }
        if (!isAgentPath(url.pathname)) {
          send({ status: 404, body: errorBody("not_found", "Không tìm thấy đường dẫn này.") });
          return;
        }
        send(await answerAgent(agentRouters, req, res, url));
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
