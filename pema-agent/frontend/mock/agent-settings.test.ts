// The fake agent's settings and tool switches behave like the backend's: null gives a field back to the profile,
// a saved value flips its source to "db", a time zone or a {{placeholder}} without a value is refused with 422.
import { beforeEach, describe, expect, it } from "vitest";

import { registerAgentSettings, resetAgentSettings } from "./agent-settings";
import { Router, type Ctx } from "./core";

const router = new Router();
registerAgentSettings(router);

async function call(method: string, path: string, body: unknown = {}) {
  const found = router.match(method, path);
  if (!found) throw new Error(`no route ${method} ${path}`);
  const ctx = { params: found.params, query: new URLSearchParams(), body } as unknown as Ctx;
  return found.route.handler(ctx);
}

type Shown = {
  timezone: string;
  variables: Record<string, string>;
  sources: Record<string, string>;
  stored: boolean;
  updated_by: string | null;
};

beforeEach(resetAgentSettings);

describe("settings routes", () => {
  it("starts_from_the_profile_with_nothing_stored", async () => {
    const shown = (await call("GET", "/v1/admin/settings")).body as Shown;

    expect(shown.stored).toBe(false);
    expect(Object.values(shown.sources).every((source) => source === "profile")).toBe(true);
  });

  it("marks_a_saved_field_as_db_and_gives_it_back_to_the_profile_with_null", async () => {
    const saved = (await call("PATCH", "/v1/admin/settings", { timezone: "Asia/Bangkok" }))
      .body as Shown;
    const back = (await call("PATCH", "/v1/admin/settings", { timezone: null })).body as Shown;

    expect([saved.timezone, saved.sources.timezone, saved.stored, saved.updated_by]).toEqual([
      "Asia/Bangkok",
      "db",
      true,
      "owner@pema.test",
    ]);
    expect([back.timezone, back.sources.timezone, back.stored]).toEqual([
      "Asia/Ho_Chi_Minh",
      "profile",
      false,
    ]);
  });

  it("refuses_an_unknown_time_zone_with_422_and_keeps_what_was_stored", async () => {
    const refused = await call("PATCH", "/v1/admin/settings", { timezone: "Mars/Olympus" });
    const shown = (await call("GET", "/v1/admin/settings")).body as Shown;

    expect(refused.status).toBe(422);
    expect(refused.body).toEqual({
      error: { kind: "invalid", message: "unknown time zone 'Mars/Olympus'" },
    });
    expect(shown.stored).toBe(false);
  });

  it("refuses_a_persona_that_uses_a_variable_without_a_value", async () => {
    const refused = await call("PATCH", "/v1/admin/settings", {
      persona: "Xin chào từ {{ten_khac}}",
    });

    expect(refused.status).toBe(422);
    expect(refused.body).toEqual({
      error: { kind: "invalid", message: "persona uses {{ten_khac}} with no value" },
    });
  });

  it("accepts_that_persona_once_the_variable_has_a_value_and_refuses_removing_that_value_again", async () => {
    await call("PATCH", "/v1/admin/settings", {
      persona: "Xin chào từ {{ten_khac}}",
      variables: { ten_khac: "Pema" },
    });
    const stillUsed = await call("PATCH", "/v1/admin/settings", { variables: { ten_khac: null } });

    expect(stillUsed.status).toBe(422);
  });

  it("clears_everything_stored_with_delete", async () => {
    await call("PATCH", "/v1/admin/settings", {
      failure_reply: "Bận",
      variables: { tone: "vui vẻ" },
    });
    await call("PUT", "/v1/admin/tools/kb_search", { enabled: false });
    const cleared = (await call("DELETE", "/v1/admin/settings")).body as Shown;
    const tools = (await call("GET", "/v1/admin/tools")).body as {
      tools: { name: string; enabled: boolean }[];
    };

    expect(cleared.stored).toBe(false);
    expect(cleared.variables.tone).toBe("lịch sự, ngắn gọn");
    expect(tools.tools.find((tool) => tool.name === "kb_search")?.enabled).toBe(true);
  });
});

describe("tool routes", () => {
  type Tool = { name: string; enabled: boolean; stored: boolean; default: boolean; source: string };
  const listed = async () =>
    ((await call("GET", "/v1/admin/tools")).body as { tools: Tool[] }).tools;

  it("lists_the_core_tools_then_memory_then_the_plugins_tools", async () => {
    const names = (await listed()).map((tool) => `${tool.source}:${tool.name}`);

    expect(names).toEqual([
      "core:get_datetime",
      "core:web_fetch",
      "core:memory",
      "plugin:kb_search",
      "plugin:skill_write",
      "plugin:zalo_send_message",
    ]);
  });

  it("switches_a_tool_off_marks_it_stored_and_gives_it_back_with_null", async () => {
    await call("PUT", "/v1/admin/tools/kb_search", { enabled: false });
    const off = (await listed()).find((tool) => tool.name === "kb_search");
    await call("PUT", "/v1/admin/tools/kb_search", { enabled: null });
    const back = (await listed()).find((tool) => tool.name === "kb_search");

    expect([off?.enabled, off?.stored]).toEqual([false, true]);
    expect([back?.enabled, back?.stored]).toEqual([true, false]);
  });

  it("switches_the_memory_tool_through_the_memory_setting", async () => {
    await call("PUT", "/v1/admin/tools/memory", { enabled: false });
    const shown = (await call("GET", "/v1/admin/settings")).body as {
      memory_enabled: boolean;
      sources: Record<string, string>;
    };

    expect([shown.memory_enabled, shown.sources.memory_enabled]).toEqual([false, "db"]);
  });

  it("answers_404_unknown_tool_for_a_name_it_does_not_have", async () => {
    const missing = await call("PUT", "/v1/admin/tools/no_such_tool", { enabled: true });

    expect(missing.status).toBe(404);
    expect(missing.body).toMatchObject({ error: { kind: "unknown_tool" } });
  });
});
