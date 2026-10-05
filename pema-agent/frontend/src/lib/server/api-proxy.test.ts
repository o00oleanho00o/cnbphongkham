// Pema addition. The proxy is tested against a real local HTTP server (node:http), so streaming, several
// Set-Cookie headers and hop-by-hop handling are the real thing, not a mock of fetch.
import { createServer, type IncomingHttpHeaders, type Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  apiBaseUrl,
  forwardToApi,
  requestHeadersForUpstream,
  resolveUpstream,
} from "@/lib/server/api-proxy";

const BASE = "http://api.internal:8000";

describe("apiBaseUrl", () => {
  it("reads the environment it is given on every call, internal url first", () => {
    expect(apiBaseUrl({ PEMA_API_INTERNAL_URL: "http://a:1", PEMA_API_URL: "http://b:2" })).toBe(
      "http://a:1",
    );
    expect(apiBaseUrl({ PEMA_API_URL: "http://b:2" })).toBe("http://b:2");
    expect(apiBaseUrl({ PEMA_API_INTERNAL_URL: "  ", PEMA_API_URL: "http://b:2" })).toBe(
      "http://b:2",
    );
    expect(apiBaseUrl({})).toBe("http://127.0.0.1:8000");
  });
});

describe("resolveUpstream", () => {
  it("forwards /api/v1 paths with the query string untouched", () => {
    const result = resolveUpstream("/api/v1/me", "?a=1&b=%20x", BASE);
    expect(result).toEqual({
      ok: true,
      url: new URL("http://api.internal:8000/api/v1/me?a=1&b=%20x"),
    });
  });

  it("forwards /healthz and keeps a sub-path of the base", () => {
    expect(resolveUpstream("/healthz", "", "http://h:9/prefix/")).toEqual({
      ok: true,
      url: new URL("http://h:9/prefix/healthz"),
    });
  });

  it("refuses anything outside /api/v1 and /healthz", () => {
    for (const path of ["/api/other", "/api", "/api/v1", "/admin", "/api/v2/x", "/docs"]) {
      expect(resolveUpstream(path, "", BASE)).toMatchObject({ ok: false, status: 404 });
    }
  });

  it("refuses dot segments, also percent-encoded and double-encoded decodings, slashes and NUL", () => {
    const bad = [
      "/api/v1/../admin",
      "/api/v1/./me",
      "/api/v1/%2e%2e/admin",
      "/api/v1/%2E%2E/admin",
      "/api/v1/.%2e/admin",
      "/api/v1/a%2f..%2fb",
      "/api/v1/a%5c..%5cb",
      "/api/v1/a%00b",
      "/api/v1/%E0%A4%A",
    ];
    for (const path of bad) {
      expect(resolveUpstream(path, "", BASE), path).toMatchObject({ ok: false, status: 400 });
    }
  });

  it("allows a literal percent sign that decodes to a dot-like text (double encoding is the API's business)", () => {
    expect(resolveUpstream("/api/v1/%252e%252e/x", "", BASE)).toMatchObject({ ok: true });
  });

  it("answers 502 when the configured address is not an http(s) url", () => {
    for (const base of ["", "not a url", "file:///etc/passwd", "ftp://x"]) {
      expect(resolveUpstream("/api/v1/me", "", base)).toMatchObject({ ok: false, status: 502 });
    }
  });
});

describe("requestHeadersForUpstream", () => {
  it("drops hop-by-hop, per-connection and forgeable headers, keeps cookies and content headers", () => {
    const out = requestHeadersForUpstream(
      new Headers({
        connection: "keep-alive, x-custom-hop",
        "x-custom-hop": "1",
        "keep-alive": "timeout=5",
        te: "trailers",
        upgrade: "websocket",
        "transfer-encoding": "chunked",
        "proxy-authorization": "Basic Zm9v",
        host: "evil.example",
        "x-forwarded-for": "6.6.6.6",
        "x-forwarded-host": "evil.example",
        "x-real-ip": "6.6.6.6",
        forwarded: "for=6.6.6.6",
        "accept-encoding": "gzip",
        cookie: "pema_session=abc",
        "content-type": "application/json",
        "x-request-id": "r1",
      }),
    );
    expect([...out.keys()].toSorted()).toEqual(["content-type", "cookie", "x-request-id"]);
  });
});

describe("forwardToApi against a real server", () => {
  let server: Server;
  let baseUrl = "";
  const seen: { method?: string; url?: string; headers: IncomingHttpHeaders; body: string }[] = [];

  beforeAll(async () => {
    server = createServer((req, res) => {
      const chunks: Buffer[] = [];
      req.on("data", (chunk: Buffer) => chunks.push(chunk));
      req.on("end", () => {
        seen.push({
          method: req.method,
          url: req.url,
          headers: req.headers,
          body: Buffer.concat(chunks).toString("utf8"),
        });
        if (req.url?.startsWith("/api/v1/login")) {
          res.setHeader("set-cookie", [
            "pema_session=tok; Path=/; HttpOnly; Secure; SameSite=Lax",
            "other=1; Path=/x",
          ]);
          res.writeHead(200, {
            "content-type": "application/json",
            connection: "close",
            "x-keep": "yes",
          });
          res.end('{"ok":true}');
          return;
        }
        if (req.url?.startsWith("/api/v1/redirect")) {
          res.writeHead(307, { location: `${baseUrl}/api/v1/elsewhere?x=1` });
          res.end();
          return;
        }
        if (req.url?.startsWith("/api/v1/nocontent")) {
          res.writeHead(204);
          res.end();
          return;
        }
        if (req.url?.startsWith("/api/v1/denied")) {
          res.writeHead(401, { "content-type": "application/json" });
          res.end('{"error":{"code":"unauthenticated","message":"Chưa đăng nhập"}}');
          return;
        }
        res.writeHead(200, { "content-type": "text/plain" });
        res.end(`echo ${req.method} ${req.url}`);
      });
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    baseUrl = `http://127.0.0.1:${(server.address() as AddressInfo).port}`; // listen(0) on a TCP server: AddressInfo
  });

  afterAll(async () => {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  });

  const env = () => ({ PEMA_API_INTERNAL_URL: baseUrl });

  it("forwards method, query, headers and body, and strips forged forwarding headers", async () => {
    seen.length = 0;
    const response = await forwardToApi(
      new Request("http://web.local/api/v1/patients?q=an", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          cookie: "pema_session=abc",
          "x-forwarded-for": "6.6.6.6",
          "x-real-ip": "6.6.6.6",
          host: "web.local",
        },
        body: '{"name":"An"}',
      }),
      { env: env() },
    );
    expect(response.status).toBe(200);
    expect(await response.text()).toBe("echo POST /api/v1/patients?q=an");
    const [call] = seen;
    expect(call?.method).toBe("POST");
    expect(call?.body).toBe('{"name":"An"}');
    expect(call?.headers.cookie).toBe("pema_session=abc");
    expect(call?.headers["content-type"]).toBe("application/json");
    expect(call?.headers["x-forwarded-for"]).toBeUndefined();
    expect(call?.headers["x-real-ip"]).toBeUndefined();
    expect(call?.headers.host).toBe(new URL(baseUrl).host);
  });

  it("keeps every Set-Cookie as its own header and drops hop-by-hop headers of the answer", async () => {
    const response = await forwardToApi(
      new Request("http://web.local/api/v1/login", { method: "POST", body: "{}" }),
      { env: env() },
    );
    expect(response.headers.getSetCookie()).toEqual([
      "pema_session=tok; Path=/; HttpOnly; Secure; SameSite=Lax",
      "other=1; Path=/x",
    ]);
    expect(response.headers.get("connection")).toBeNull();
    expect(response.headers.get("x-keep")).toBe("yes");
    expect(await response.json()).toEqual({ ok: true });
  });

  it("passes status codes and bodies of errors through (401 stays 401)", async () => {
    const response = await forwardToApi(new Request("http://web.local/api/v1/denied"), {
      env: env(),
    });
    expect(response.status).toBe(401);
    expect(await response.text()).toContain("unauthenticated");
  });

  it("does not follow redirects and rewrites an absolute Location of the API to a relative one", async () => {
    const response = await forwardToApi(new Request("http://web.local/api/v1/redirect"), {
      env: env(),
    });
    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("/api/v1/elsewhere?x=1");
  });

  it("returns a body-less 204 and answers HEAD without a body", async () => {
    const noContent = await forwardToApi(new Request("http://web.local/api/v1/nocontent"), {
      env: env(),
    });
    expect(noContent.status).toBe(204);
    expect(noContent.body).toBeNull();
    const head = await forwardToApi(new Request("http://web.local/api/v1/x", { method: "HEAD" }), {
      env: env(),
    });
    expect(head.status).toBe(200);
    expect(await head.text()).toBe("");
  });

  it("reads the API address on every call: two environments, two destinations", async () => {
    const other = createServer((_req, res) => {
      res.end("second api");
    });
    await new Promise<void>((resolve) => other.listen(0, "127.0.0.1", resolve));
    const otherUrl = `http://127.0.0.1:${(other.address() as AddressInfo).port}`; // TCP server: AddressInfo
    try {
      const request = () => new Request("http://web.local/healthz");
      const first = await forwardToApi(request(), { env: env() });
      const second = await forwardToApi(request(), { env: { PEMA_API_INTERNAL_URL: otherUrl } });
      expect(await first.text()).toBe("echo GET /healthz");
      expect(await second.text()).toBe("second api");
    } finally {
      await new Promise<void>((resolve) => other.close(() => resolve()));
    }
  });

  it("refuses traversal before any request reaches the API", async () => {
    seen.length = 0;
    const response = await forwardToApi(
      new Request("http://web.local/api/v1/%2e%2e/%2e%2e/admin/users"),
      { env: env() },
    );
    expect([400, 404]).toContain(response.status);
    expect(seen).toHaveLength(0);
  });

  it("answers 502 with the API error shape when the API is down", async () => {
    const response = await forwardToApi(new Request("http://web.local/api/v1/me"), {
      env: { PEMA_API_INTERNAL_URL: "http://127.0.0.1:1" },
    });
    expect(response.status).toBe(502);
    const body = (await response.json()) as { error: { code: string; message: string } };
    expect(body.error.code).toBe("internal");
    expect(body.error.message).not.toContain("127.0.0.1");
  });
});
