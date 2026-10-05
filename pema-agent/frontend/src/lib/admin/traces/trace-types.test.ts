import { describe, expect, it } from "vitest";

import type { Schemas } from "@/lib/api";

import { traceStepTuApi } from "./trace-types";

const ROW: Schemas["TraceStepRow"] = {
  id: 1,
  turn_id: 9,
  step_number: 2,
  created_at: "2026-09-20T09:00:00+07:00",
  attempt: 2,
  finish_reason: "tool-calls",
  input_tokens: 1200,
  output_tokens: 80,
  reasoning: "",
  text: "Em tra kho nhé",
  warnings: ["temperature bị bỏ qua"],
  tool_calls: [{ name: "kb_search", input: { query: "chăm sóc sau laser" } }],
  tool_results: [
    { name: "kb_search", output: "3 đoạn", hong: false },
    { name: "web_fetch", output: "lỗi", is_error: true },
  ],
  tool_errors: [{ name: "web_fetch", error: "hết thời gian" }],
};

describe("trace step from the API", () => {
  it("names_and_counters_are_carried_over", () => {
    const step = traceStepTuApi(ROW);
    expect([step.stepNumber, step.attempt, step.inputTokens, step.outputTokens]).toEqual([
      2, 2, 1200, 80,
    ]);
  });

  it("a_tool_input_that_is_an_object_is_shown_as_json_text", () => {
    expect(traceStepTuApi(ROW).toolCalls[0]?.input).toContain('"query": "chăm sóc sau laser"');
  });

  it("a_failed_tool_result_is_flagged_by_hong_or_is_error", () => {
    expect(traceStepTuApi(ROW).toolResults.map((r) => r.hong)).toEqual([false, true]);
  });

  it("tool_errors_keep_name_and_message", () => {
    expect(traceStepTuApi(ROW).toolErrors).toEqual([{ name: "web_fetch", error: "hết thời gian" }]);
  });

  it("missing_optional_parts_become_empty_values", () => {
    const step = traceStepTuApi({
      id: 2,
      turn_id: 9,
      step_number: 1,
      created_at: ROW.created_at,
      attempt: 1,
      finish_reason: "",
      input_tokens: 0,
      output_tokens: 0,
      reasoning: "",
      text: "",
    });
    expect([step.text, step.warnings, step.toolCalls, step.attempt]).toEqual(["", [], [], 1]);
  });
});
