// What the overview's model warning lists as missing.
import { describe, expect, it } from "vitest";

import { missingModelParts } from "./model-status";

const SET = {
  provider: "openai-compatible",
  model: "deepseek-chat",
  base_url: null,
  api_key: "sk-…1234",
  api_key_broken: false,
};

describe("missingModelParts", () => {
  it("is_empty_when_a_model_and_a_key_are_set_even_without_a_base_url", () => {
    expect(missingModelParts(SET)).toEqual([]);
  });

  it("lists_the_model_name_and_the_key_when_both_are_missing", () => {
    expect(missingModelParts({ ...SET, model: "  ", api_key: "" })).toEqual([
      "tên model",
      "khóa API",
    ]);
  });

  it("asks_for_the_key_again_when_the_stored_one_cannot_be_read", () => {
    expect(missingModelParts({ ...SET, api_key_broken: true })).toEqual([
      "khóa API đã lưu không đọc được (nhập lại)",
    ]);
  });
});
