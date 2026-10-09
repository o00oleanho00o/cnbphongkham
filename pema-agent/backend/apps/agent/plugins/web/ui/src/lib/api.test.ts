import { describe, expect, it } from "vitest";

import { ApiError, createApi, errorText } from "./api";

describe("errorText", () => {
  it("reads the gateway's, the plugin routes' and the validation shapes", () => {
    expect(errorText({ error: { kind: "x", message: "the gateway says" } }, 500)).toBe("the gateway says");
    expect(errorText({ detail: "a plugin says" }, 409)).toBe("a plugin says");
    expect(errorText({ detail: [{ msg: "too short" }, { msg: "bad email" }] }, 422)).toBe("too short; bad email");
    expect(errorText("plain", 502)).toBe("Lỗi 502");
  });
});

describe("createApi", () => {
  it("sends JSON, reads JSON and an empty answer, and raises the server's words", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const answers = [
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
      new Response(null, { status: 204 }),
      new Response(JSON.stringify({ detail: "Không có API key này" }), { status: 404 }),
    ];
    const api = createApi(async (url, init) => {
      calls.push({ url: String(url), init: init ?? {} });
      return answers.shift() ?? new Response(null, { status: 500 });
    });

    const first = await api.post<{ ok: boolean }>("/v1/x", { a: 1 });
    const second = await api.del("/v1/y");
    const failed = await api.get("/v1/z").catch((err: unknown) => err);

    expect(first).toEqual({ ok: true });
    expect(second).toBeUndefined();
    expect(failed).toBeInstanceOf(ApiError);
    expect((failed as ApiError).status).toBe(404);
    expect((failed as ApiError).message).toBe("Không có API key này");
    expect(calls[0]?.init.body).toBe('{"a":1}');
    expect(new Headers(calls[0]?.init.headers).get("Content-Type")).toBe("application/json");
    expect(new Headers(calls[1]?.init.headers).has("Content-Type")).toBe(false);
  });
});
