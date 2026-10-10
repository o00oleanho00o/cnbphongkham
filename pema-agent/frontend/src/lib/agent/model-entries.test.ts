// The rules the Model page lists the agent's models by: the provider a model belongs to, the label a new one gets,
// and the grouping.
import { describe, expect, it } from "vitest";

import { brandCounts, brandOf, groupByBrand, type ModelEntry, nextLabel } from "./model-entries";

const entry = (label: string, provider: string, base_url: string | null): ModelEntry => ({
  id: label,
  label,
  provider,
  model: "m",
  base_url,
  reasoning: null,
  dialect: null,
  api_key: "",
  has_key: false,
  api_key_broken: false,
  active: false,
});

const DEEPSEEK = "https://api.deepseek.com";

describe("brandOf", () => {
  it("names_the_provider_by_its_address_or_by_the_anthropic_default", () => {
    expect(brandOf(entry("a", "openai-compatible", DEEPSEEK))).toBe("DeepSeek");
    expect(brandOf(entry("b", "anthropic", null))).toBe("Anthropic");
  });

  it("names_an_unknown_address_by_its_host_and_no_address_as_other", () => {
    expect(brandOf(entry("a", "openai-compatible", "https://llm.noi-bo.test/v1"))).toBe(
      "llm.noi-bo.test",
    );
    expect(brandOf(entry("b", "openai-compatible", null))).toBe("Khác");
  });
});

describe("nextLabel", () => {
  it("offers_the_plain_name_for_the_first_model_of_a_provider", () => {
    expect(nextLabel("DeepSeek", [])).toBe("DeepSeek");
  });

  it("counts_the_models_of_that_provider_already_in_the_list", () => {
    const list = [
      entry("công ty", "openai-compatible", DEEPSEEK),
      entry("dự phòng", "openai-compatible", DEEPSEEK),
      entry("khác", "anthropic", null),
    ];

    expect(nextLabel("DeepSeek", list)).toBe("DeepSeek 3");
  });

  it("skips_a_label_that_is_taken", () => {
    const list = [entry("DeepSeek 2", "openai-compatible", DEEPSEEK)];

    expect(nextLabel("DeepSeek", list)).toBe("DeepSeek 3");
  });
});

describe("groupByBrand", () => {
  it("groups_models_by_provider_in_the_order_each_first_appears_and_counts_them", () => {
    const list = [
      entry("1", "openai-compatible", DEEPSEEK),
      entry("2", "anthropic", null),
      entry("3", "openai-compatible", DEEPSEEK),
    ];

    expect(groupByBrand(list).map((g) => [g.brand, g.entries.map((e) => e.label)])).toEqual([
      ["DeepSeek", ["1", "3"]],
      ["Anthropic", ["2"]],
    ]);
    expect(brandCounts(list)).toBe("2 DeepSeek · 1 Anthropic");
  });
});
