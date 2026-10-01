import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import { tuningTuApi } from "./tuning-types";

const OUT: Schemas["TuningOut"] = {
  groups: [{ id: "agent", title: "Agent", hint: "", nav_hint: "" }],
  items: [
    {
      key: "LLM_CONTEXT_WINDOW",
      group: "agent",
      kind: "number",
      label: "Cửa sổ",
      hint: "",
      default: 128000,
      value: 200000,
      min: 8000,
      max: 2000000,
      overridden: true,
      presets: [32000, 128000],
      token_estimate_hint: false,
    },
    {
      key: "AGENT_TRACE_ENABLED",
      group: "agent",
      kind: "boolean",
      label: "Trace",
      hint: "",
      default: true,
      value: true,
      overridden: false,
      token_estimate_hint: false,
    },
    {
      key: "BOT_TIMEZONE",
      group: "agent",
      kind: "text",
      label: "Múi giờ",
      hint: "",
      default: "Asia/Ho_Chi_Minh",
      value: "Asia/Ho_Chi_Minh",
      overridden: false,
      token_estimate_hint: false,
    },
    {
      key: "LLM_REASONING_EFFORT",
      group: "agent",
      kind: "select",
      label: "Mức suy nghĩ",
      hint: "",
      default: "off",
      value: "off",
      options: ["off", "low"],
      overridden: false,
      token_estimate_hint: false,
    },
  ],
};

describe("tuning from the API", () => {
  it("an_overridden_item_is_not_from_env_and_keeps_its_default", () => {
    const { values } = tuningTuApi(OUT);
    expect(values.LLM_CONTEXT_WINDOW).toEqual({
      key: "LLM_CONTEXT_WINDOW",
      value: 200000,
      macDinh: 128000,
      fromEnv: false,
    });
  });

  it("an_item_without_an_override_row_is_from_env", () => {
    expect(tuningTuApi(OUT).values.AGENT_TRACE_ENABLED?.fromEnv).toBe(true);
  });

  it("the_context_window_presets_keep_the_model_hints", () => {
    const def = tuningTuApi(OUT).defs.LLM_CONTEXT_WINDOW;
    expect(def?.kind === "number" && def.presets?.find((p) => p.value === 128000)?.hint).toBe(
      "phổ thông, an toàn",
    );
  });

  it("the_timezone_key_becomes_a_timezone_control", () => {
    expect(tuningTuApi(OUT).defs.BOT_TIMEZONE?.kind).toBe("timezone");
  });

  it("a_select_becomes_an_enum_with_its_options", () => {
    const def = tuningTuApi(OUT).defs.LLM_REASONING_EFFORT;
    expect(def?.kind === "enum" && def.options).toEqual(["off", "low"]);
  });

  it("the_groups_are_passed_through", () => {
    expect(tuningTuApi(OUT).groups.map((g) => g.id)).toEqual(["agent"]);
  });
});
