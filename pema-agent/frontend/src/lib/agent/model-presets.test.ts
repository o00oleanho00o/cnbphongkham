// The model presets: each one is complete enough to save once a key is added, and applying one sets the form.
import { describe, expect, it } from "vitest";

import { MODEL_PRESETS, withPreset } from "./model-presets";

const FORM = {
  provider: "openai-compatible",
  model: "old-model",
  base_url: "https://old.example",
  reasoning: "high",
  dialect: "openai",
  api_key: "",
};

describe("model presets", () => {
  it("have_distinct_ids_and_an_address_or_the_providers_default", () => {
    expect(new Set(MODEL_PRESETS.map((p) => p.id)).size).toBe(MODEL_PRESETS.length);
    MODEL_PRESETS.filter((p) => p.base_url !== "").forEach((p) => {
      expect(p.base_url).toMatch(/^https?:\/\//);
    });
  });

  it("replace_provider_address_model_and_api_kind_and_reset_the_reasoning", () => {
    const deepseek = MODEL_PRESETS.find((p) => p.id === "deepseek");
    if (!deepseek) throw new Error("the DeepSeek preset is missing");

    expect(withPreset(FORM, deepseek)).toEqual({
      provider: "openai-compatible",
      model: "deepseek-v4-pro",
      base_url: "https://api.deepseek.com",
      reasoning: "",
      dialect: "deepseek",
      api_key: "",
    });
  });
});
