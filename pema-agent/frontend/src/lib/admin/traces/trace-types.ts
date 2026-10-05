// ported from: web/src/dashboard-api-client.ts (type TraceStep)
//
// Deviation: the contract's `TraceStepRow` is snake_case and its tool calls/results/errors are free-form
// JSON objects (`JsonObject[]`), where the original had `{name, input}`, `{name, output, hong}` and
// `{name, error}`. `traceStepTuApi` reads those objects defensively and rebuilds exactly the original
// `TraceStep`, so `trace-step-card.tsx` stays as written. A value that is not text is shown as JSON.
import type { Schemas } from "@/lib/api";

type TraceStepRow = Schemas["TraceStepRow"];
type Json = Record<string, unknown>;

/** Một step trong lượt agent: model nói gì, gọi tool nào với tham số gì */
export type TraceStep = {
  stepNumber: number;
  /**
   * Lần chạy thứ mấy trong cùng lượt. > 1 nghĩa là bot đã phải chạy lại - step đánh số lại từ 1 nên không
   * có trường này thì trace đọc ra 1,1,2,2,3,3 trông như model lặp.
   */
  attempt: number;
  text: string;
  /** Rỗng với model không phơi chuỗi suy nghĩ; có với DeepSeek */
  reasoning: string;
  toolCalls: { name: string; input: string }[];
  /** `hong` là nhánh HỎNG của tool, không phải kết quả thường */
  toolResults: { name: string; output: string; hong?: boolean }[];
  toolErrors: { name: string; error: string }[];
  finishReason: string;
  /** Nhà cung cấp báo tham số bị bỏ qua - chỗ hay lộ lỗi âm thầm */
  warnings: string[];
  inputTokens: number;
  outputTokens: number;
};

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === undefined || value === null) return "";
  return JSON.stringify(value, null, 2);
}

function nameOf(entry: Json): string {
  return typeof entry.name === "string" && entry.name ? entry.name : "(không tên)";
}

export function traceStepTuApi(row: TraceStepRow): TraceStep {
  return {
    stepNumber: row.step_number,
    attempt: row.attempt ?? 1,
    text: row.text ?? "",
    reasoning: row.reasoning ?? "",
    toolCalls: (row.tool_calls ?? []).map((c: Json) => ({
      name: nameOf(c),
      input: asText(c.input ?? c.arguments),
    })),
    toolResults: (row.tool_results ?? []).map((r: Json) => ({
      name: nameOf(r),
      output: asText(r.output ?? r.result),
      hong: r.hong === true || r.is_error === true,
    })),
    toolErrors: (row.tool_errors ?? []).map((e: Json) => ({
      name: nameOf(e),
      error: asText(e.error ?? e.message),
    })),
    finishReason: row.finish_reason ?? "",
    warnings: row.warnings ?? [],
    inputTokens: row.input_tokens ?? 0,
    outputTokens: row.output_tokens ?? 0,
  };
}
