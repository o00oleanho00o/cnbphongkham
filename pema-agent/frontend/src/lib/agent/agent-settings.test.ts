// What the Cài đặt page sends and refuses: a save carries only the fields that changed, variables go by name, and
// the page refuses a bad value before the agent does.
import { describe, expect, it } from "vitest";

import {
  type AgentSettings,
  draftErrors,
  draftOf,
  isAgentSettings,
  isStored,
  patchOf,
  takeFields,
} from "./agent-settings";

const SHOWN: AgentSettings = {
  timezone: "Asia/Ho_Chi_Minh",
  failure_reply: "Xin lỗi, hệ thống đang bận.",
  variables: { clinic_name: "Pema", tone: "lịch sự" },
  persona: "Bạn là trợ lý của {{clinic_name}}.",
  rules: "Không chẩn đoán.",
  memory_enabled: true,
  memory_agent_chars: 2200,
  memory_user_chars: 1400,
  sources: {
    timezone: "profile",
    failure_reply: "profile",
    variables: "profile",
    persona: "db",
    rules: "profile",
    memory_enabled: "profile",
    memory_agent_chars: "profile",
    memory_user_chars: "profile",
  },
  stored: true,
  version: 3,
  updated_by: "owner@pema.test",
};

describe("patchOf", () => {
  it("is_empty_when_nothing_was_edited", () => {
    expect(patchOf(draftOf(SHOWN), SHOWN)).toEqual({});
  });

  it("sends_only_the_fields_that_changed", () => {
    const draft = { ...draftOf(SHOWN), timezone: "Asia/Bangkok", memory_user_chars: "3000" };

    expect(patchOf(draft, SHOWN)).toEqual({ timezone: "Asia/Bangkok", memory_user_chars: 3000 });
  });

  it("sends_the_memory_switch_as_a_boolean", () => {
    expect(patchOf({ ...draftOf(SHOWN), memory_enabled: false }, SHOWN)).toEqual({
      memory_enabled: false,
    });
  });

  it("sends_only_the_variables_that_changed_or_were_added", () => {
    const base = draftOf(SHOWN);
    const draft = {
      ...base,
      variables: [
        { name: "clinic_name", value: "Pema", isNew: false },
        { name: "tone", value: "thân thiện", isNew: false },
        { name: "hotline", value: "0900 000 000", isNew: true },
        { name: "", value: "", isNew: true },
      ],
    };

    expect(patchOf(draft, SHOWN)).toEqual({
      variables: { tone: "thân thiện", hotline: "0900 000 000" },
    });
  });
});

describe("draftErrors", () => {
  it("has_none_for_the_shown_settings", () => {
    expect(draftErrors(draftOf(SHOWN))).toEqual({});
  });

  it("refuses_an_empty_time_zone_and_a_memory_size_out_of_range", () => {
    const draft = {
      ...draftOf(SHOWN),
      timezone: " ",
      memory_agent_chars: "50",
      memory_user_chars: "abc",
    };

    expect(Object.keys(draftErrors(draft)).sort()).toEqual([
      "memory_agent_chars",
      "memory_user_chars",
      "timezone",
    ]);
  });

  it("refuses_a_bad_name_a_taken_name_and_an_empty_value_of_a_variable", () => {
    const rows = (name: string, value: string) => ({
      ...draftOf(SHOWN),
      variables: [...draftOf(SHOWN).variables, { name, value, isNew: true }],
    });

    expect(draftErrors(rows("Bad Name", "x")).variables).toMatch(/Tên biến/);
    expect(draftErrors(rows("tone", "x")).variables).toBe("Tên biến bị trùng");
    expect(draftErrors(rows("hotline", " ")).variables).toMatch(/Giá trị/);
    expect(draftErrors(rows("hotline", "0900")).variables).toBeUndefined();
  });
});

describe("takeFields", () => {
  it("replaces_only_the_named_fields_and_keeps_what_is_being_typed", () => {
    const typing = { ...draftOf(SHOWN), failure_reply: "đang gõ", persona: "đã sửa dở" };
    const fresh = { ...SHOWN, persona: "Bản của file" };

    const next = takeFields(typing, fresh, ["persona"]);

    expect([next.persona, next.failure_reply]).toEqual(["Bản của file", "đang gõ"]);
  });
});

describe("source and shape", () => {
  it("knows_a_field_kept_in_the_system_from_one_that_follows_the_profile", () => {
    expect([isStored(SHOWN, "persona"), isStored(SHOWN, "rules")]).toEqual([true, false]);
  });

  it("recognises_an_answer_of_the_settings_route", () => {
    expect([
      isAgentSettings(SHOWN),
      isAgentSettings({ error: "x" }),
      isAgentSettings(null),
    ]).toEqual([true, false, false]);
  });
});
