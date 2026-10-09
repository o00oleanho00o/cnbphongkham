// Pema addition (plan C). The agent proxy: which paths reach the agent, and how a clinic session becomes a short
// agent token that the agent sees instead of the cookie.
import { describe, expect, it } from "vitest";

import {
  AgentTokens,
  agentBaseUrl,
  forwardToAgent,
  resolveAgentUpstream,
  sessionOf,
} from "@/lib/server/agent-proxy";

const AGENT = "http://agent.internal:8088";
const ENV = { PEMA_API_INTERNAL_URL: "http://api.internal:8000", PEMA_AGENT_INTERNAL_URL: AGENT };
const TOKEN_URL = "http://api.internal:8000/api/v1/auth/agent-token";
const NOW = Date.parse("2026-10-10T09:00:00Z");

interface Call {
  url: string;
  method: string;
  headers: Headers;
}

/** The clinic API and the agent, answering from the tables given; every call is recorded. */
function services(
  agent: (url: string) => Response = () => Response.json({ ok: true }),
  tokenAnswer: () => Response = () =>
    Response.json({ token: "agent-token-1", expires_at: new Date(NOW + 120_000).toISOString() }),
) {
  const calls: Call[] = [];
  const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, method: init?.method ?? "GET", headers: new Headers(init?.headers) });
    return url === TOKEN_URL ? tokenAnswer() : agent(url);
  }) as typeof fetch;
  return { calls, fetchImpl };
}

function browser(path: string, headers: Record<string, string> = {}): Request {
  return new Request(`http://web.test${path}`, {
    headers: { cookie: "theme=dark; pema_session=s3ss=ion", ...headers },
  });
}

describe("resolveAgentUpstream", () => {
  it("forwards only the agent's API and plugin pages, with the query", () => {
    expect(resolveAgentUpstream("/agent/v1/admin/plugins", "?a=1", AGENT)).toEqual({
      ok: true,
      url: new URL(`${AGENT}/v1/admin/plugins?a=1`),
    });
    expect(resolveAgentUpstream("/agent/ui/zalo/client.js", "", `${AGENT}/sub/`)).toEqual({
      ok: true,
      url: new URL(`${AGENT}/sub/ui/zalo/client.js`),
    });
    expect(resolveAgentUpstream("/agent/healthz", "", AGENT)).toMatchObject({ status: 404 });
    expect(resolveAgentUpstream("/agent", "", AGENT)).toMatchObject({ status: 404 });
    expect(resolveAgentUpstream("/api/v1/me", "", AGENT)).toMatchObject({ status: 404 });
  });

  it("refuses paths that could climb out and a bad address", () => {
    for (const path of [
      "/agent/v1/../healthz",
      "/agent/v1/%2e%2e/x",
      "/agent/ui/a%2fb",
      "/agent/v1/%zz",
    ]) {
      expect(resolveAgentUpstream(path, "", AGENT)).toMatchObject({ ok: false });
    }
    expect(resolveAgentUpstream("/agent/v1/x", "", "ftp://agent")).toMatchObject({ status: 502 });
  });

  it("reads the agent address on every call", () => {
    expect(agentBaseUrl({ PEMA_AGENT_INTERNAL_URL: " http://a:1 " })).toBe("http://a:1");
    expect(agentBaseUrl({})).toBe("http://127.0.0.1:8088");
  });
});

describe("sessionOf", () => {
  it("finds the session cookie among others, keeping '=' in its value", () => {
    expect(sessionOf("a=1; pema_session=x=y; b=2")).toBe("x=y");
    expect(sessionOf("a=1")).toBeNull();
    expect(sessionOf(null)).toBeNull();
  });
});

describe("forwardToAgent", () => {
  it("swaps the cookie for one agent token per session and streams the answer", async () => {
    const { calls, fetchImpl } = services();
    const tokens = new AgentTokens(() => NOW);

    const first = await forwardToAgent(
      browser("/agent/v1/admin/plugins", { "x-forwarded-for": "1.2.3.4" }),
      {
        env: ENV,
        fetchImpl,
        tokens,
      },
    );
    const second = await forwardToAgent(browser("/agent/ui/zalo/client.js"), {
      env: ENV,
      fetchImpl,
      tokens,
    });

    expect([first.status, second.status]).toEqual([200, 200]);
    expect(await first.json()).toEqual({ ok: true });
    expect(calls.map((c) => c.url)).toEqual([
      TOKEN_URL,
      `${AGENT}/v1/admin/plugins`,
      `${AGENT}/ui/zalo/client.js`,
    ]);
    const [asked, forwarded] = calls;
    expect(asked?.method).toBe("POST");
    expect(asked?.headers.get("cookie")).toBe("pema_session=s3ss=ion");
    expect(forwarded?.headers.get("cookie")).toBeNull();
    expect(forwarded?.headers.get("x-forwarded-for")).toBeNull();
    expect(forwarded?.headers.get("authorization")).toBe("Bearer agent-token-1");
  });

  it("asks again when the token is about to expire or the agent refused it", async () => {
    let now = NOW;
    let agentStatus = 200;
    const { calls, fetchImpl } = services(
      () => new Response(null, { status: agentStatus }),
      () => Response.json({ token: "t", expires_at: new Date(now + 120_000).toISOString() }),
    );
    const tokens = new AgentTokens(() => now);
    const go = () => forwardToAgent(browser("/agent/v1/x"), { env: ENV, fetchImpl, tokens });

    await go();
    now += 101_000;
    await go();
    agentStatus = 401;
    await go();
    agentStatus = 200;
    await go();

    expect(calls.filter((c) => c.url === TOKEN_URL)).toHaveLength(3);
  });

  it("asks once for calls that come together", async () => {
    const { calls, fetchImpl } = services();
    const tokens = new AgentTokens(() => NOW);

    await Promise.all(
      [1, 2, 3].map(() => forwardToAgent(browser("/agent/v1/x"), { env: ENV, fetchImpl, tokens })),
    );

    expect(calls.filter((c) => c.url === TOKEN_URL)).toHaveLength(1);
  });

  it("refuses without a session and passes the API's refusal through, never calling the agent", async () => {
    const forbidden = {
      error: { code: "forbidden", message: "Bạn không có quyền quản trị agent." },
    };
    const { calls, fetchImpl } = services(undefined, () =>
      Response.json(forbidden, { status: 403 }),
    );
    const tokens = new AgentTokens(() => NOW);

    const anonymous = await forwardToAgent(new Request("http://web.test/agent/v1/x"), {
      env: ENV,
      fetchImpl,
      tokens,
    });
    const refused = await forwardToAgent(browser("/agent/v1/x"), { env: ENV, fetchImpl, tokens });

    expect(anonymous.status).toBe(401);
    expect(refused.status).toBe(403);
    expect(await refused.json()).toEqual(forbidden);
    expect(calls.map((c) => c.url)).toEqual([TOKEN_URL]);
  });

  it("answers 502 when the API gives no token or the agent cannot be reached", async () => {
    const tokens = new AgentTokens(() => NOW);
    const broken = services(undefined, () => Response.json({ token: 1 }));
    const down = services(() => {
      throw new TypeError("fetch failed");
    });

    const noToken = await forwardToAgent(browser("/agent/v1/x"), { env: ENV, ...broken, tokens });
    const noAgent = await forwardToAgent(browser("/agent/v1/x"), { env: ENV, ...down, tokens });

    expect([noToken.status, noAgent.status]).toEqual([502, 502]);
  });

  it("keeps a redirect inside /agent and drops cookies the agent sets", async () => {
    const { fetchImpl } = services(
      () =>
        new Response(null, {
          status: 307,
          headers: { location: `${AGENT}/ui/web/`, "set-cookie": "x=1" },
        }),
    );

    const answer = await forwardToAgent(browser("/agent/ui/web"), {
      env: ENV,
      fetchImpl,
      tokens: new AgentTokens(() => NOW),
    });

    expect(answer.headers.get("location")).toBe("/agent/ui/web/");
    expect(answer.headers.get("set-cookie")).toBeNull();
  });
});
