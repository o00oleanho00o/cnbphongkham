import { describe, expect, it, vi } from "vitest";

import { ApiError, createAgentApi, errorText } from "./api";

type Call = { url: string; init: RequestInit };

function fakeFetch(status: number, body: string) {
  const calls: Call[] = [];
  const fetcher = vi.fn((url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} });
    return Promise.resolve(new Response(body === "" ? null : body, { status }));
  });
  return { calls, fetcher: fetcher as unknown as typeof fetch };
}

describe("createAgentApi", () => {
  it("sends_plugin_paths_same_origin_under_agent_with_the_cookie_and_no_token", async () => {
    const { calls, fetcher } = fakeFetch(200, `[{"id":"a"}]`);
    const api = createAgentApi({ fetcher, onUnauthorized: () => undefined });

    const answer = await api.get<{ id: string }[]>("/v1/plugins/zalo/accounts");

    expect(answer).toEqual([{ id: "a" }]);
    expect(calls[0]?.url).toBe("/agent/v1/plugins/zalo/accounts");
    expect(calls[0]?.init.credentials).toBe("same-origin");
    expect(calls[0]?.init.method).toBe("GET");
    const headers = calls[0]?.init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
    expect(headers["Content-Type"]).toBeUndefined();
  });

  it("sends_a_json_body_with_each_writing_method", async () => {
    const { calls, fetcher } = fakeFetch(200, "{}");
    const api = createAgentApi({ fetcher, onUnauthorized: () => undefined });

    await api.post("/v1/x", { a: 1 });
    await api.put("/v1/x", { b: 2 });
    await api.patch("/v1/x", { c: 3 });
    await api.del("/v1/x");

    expect(calls.map((c) => c.init.method)).toEqual(["POST", "PUT", "PATCH", "DELETE"]);
    expect(calls.map((c) => c.init.body)).toEqual([`{"a":1}`, `{"b":2}`, `{"c":3}`, undefined]);
    expect((calls[0]?.init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
  });

  it("resolves_an_empty_answer_to_undefined", async () => {
    const { fetcher } = fakeFetch(204, "");
    const api = createAgentApi({ fetcher, onUnauthorized: () => undefined });

    await expect(api.del("/v1/x")).resolves.toBeUndefined();
  });

  it("throws_the_servers_own_words_with_status_and_payload", async () => {
    const payload = { error: { code: "forbidden", message: "Bạn không có quyền quản trị agent." } };
    const { fetcher } = fakeFetch(403, JSON.stringify(payload));
    const api = createAgentApi({ fetcher, onUnauthorized: () => undefined });

    const failure = await api.get("/v1/admin/ui").catch((e: unknown) => e);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(403);
    expect((failure as ApiError).message).toBe("Bạn không có quyền quản trị agent.");
    expect((failure as ApiError).payload).toEqual(payload);
  });

  it("calls_the_sign_in_handling_on_a_401_and_still_throws", async () => {
    const { fetcher } = fakeFetch(401, `{"error":{"message":"Bạn cần đăng nhập."}}`);
    const onUnauthorized = vi.fn();
    const api = createAgentApi({ fetcher, onUnauthorized });

    await expect(api.get("/v1/admin/ui")).rejects.toThrow("Bạn cần đăng nhập.");
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("does_not_call_the_sign_in_handling_on_other_errors", async () => {
    const { fetcher } = fakeFetch(500, "oops");
    const onUnauthorized = vi.fn();
    const api = createAgentApi({ fetcher, onUnauthorized });

    await expect(api.get("/v1/x")).rejects.toThrow("Lỗi 500");
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("says_the_server_cannot_be_reached_when_fetch_fails", async () => {
    const fetcher = (() => Promise.reject(new TypeError("Failed to fetch"))) as typeof fetch;
    const api = createAgentApi({ fetcher, onUnauthorized: () => undefined });

    const failure = await api.get("/v1/x").catch((e: unknown) => e);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(0);
    expect((failure as ApiError).message).toBe("Không kết nối được máy chủ.");
  });
});

describe("errorText", () => {
  it("reads_error_message_then_detail_text_then_field_errors", () => {
    expect(errorText({ error: { kind: "x", message: "Sai mã." } }, 401)).toBe("Sai mã.");
    expect(errorText({ detail: "Không có tài khoản này." }, 404)).toBe("Không có tài khoản này.");
    expect(errorText({ detail: [{ msg: "thiếu id" }, { msg: "nhãn quá dài" }] }, 422)).toBe(
      "thiếu id; nhãn quá dài",
    );
  });

  it("falls_back_to_the_status_for_anything_else", () => {
    expect(errorText("plain text", 502)).toBe("Lỗi 502");
    expect(errorText({ detail: [{ loc: ["body"] }] }, 422)).toBe("Lỗi 422");
    expect(errorText(undefined, 500)).toBe("Lỗi 500");
  });
});
