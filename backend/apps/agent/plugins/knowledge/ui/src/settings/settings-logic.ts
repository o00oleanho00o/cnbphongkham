/** Pure rules of the settings tab: ranges, forms, the patch each section sends and the words about test results. */
import type {
  EmbeddingSettings,
  EmbeddingTest,
  JevState,
  JudgeLevel,
  KnowledgeSettings,
  SettingOrigin,
  SettingsPatch,
} from "../types";

export const ORIGIN_LABEL: Record<SettingOrigin, string> = {
  saved: "Đã lưu",
  profile: "Theo cấu hình",
};

export const ORIGIN_HINT: Record<SettingOrigin, string> = {
  saved: "Giá trị bạn đã lưu ở đây",
  profile: "Giá trị theo cấu hình của agent, chưa chỉnh ở đây",
};

/** The groups that can go back to the agent's own configuration. */
export type ResettableGroup = "embedding";

/** `PATCH /settings` with `reset` puts those groups back to the configuration and forgets what was saved. */
export type SettingsChange = SettingsPatch;

/** The change that resets one group. A variable, not a literal, so it passes where only `SettingsPatch` is typed. */
export const resetChange = (group: ResettableGroup): SettingsChange => ({ reset: [group] });

// -- numbers ---------------------------------------------------------------------------------------------

export interface Range {
  label: string;
  min: number;
  max: number;
  integer: boolean;
}

export const RANGES = {
  dimensions: { label: "Số chiều", min: 32, max: 4096, integer: true },
  results: { label: "Số kết quả", min: 1, max: 50, integer: true },
  min_score: { label: "Ngưỡng điểm", min: 0, max: 1, integer: false },
  char_budget: { label: "Ngân sách ký tự", min: 500, max: 8_000, integer: true },
} satisfies Record<string, Range>;

/** The number in a box, or null when it is empty or not a number. */
export function parseNumber(text: string): number | null {
  if (text.trim() === "") return null;
  const value = Number(text.trim().replace(",", "."));
  return Number.isFinite(value) ? value : null;
}

export function numberProblem(text: string, range: Range): string | null {
  const value = parseNumber(text);
  if (value === null) return `${range.label}: nhập một số.`;
  if (range.integer && !Number.isInteger(value)) return `${range.label}: nhập số nguyên.`;
  if (value < range.min || value > range.max) return `${range.label}: từ ${range.min} đến ${range.max}.`;
  return null;
}

export function urlProblem(text: string, label: string, required: boolean): string | null {
  const value = text.trim();
  if (value === "") return required ? `${label}: nhập địa chỉ.` : null;
  return /^https?:\/\/\S+$/i.test(value) ? null : `${label}: địa chỉ bắt đầu bằng http:// hoặc https://.`;
}

export type Problems<K extends string> = Partial<Record<K, string>>;

export const hasProblems = (problems: Problems<string>): boolean => Object.values(problems).some(Boolean);

/** Fields of `after` that differ from `before`, as a patch object. */
function changed<T extends object>(before: T, after: T): Partial<T> {
  return Object.fromEntries(
    (Object.keys(after) as (keyof T)[])
      .filter((key) => after[key] !== before[key])
      .map((key) => [key, after[key]]),
  ) as Partial<T>; // keys and values both come from `after`, so the result is a subset of T
}

const isEmpty = (value: object): boolean => Object.keys(value).length === 0;

// -- embedding -------------------------------------------------------------------------------------------

export interface EmbeddingForm {
  base_url: string;
  model: string;
  /** Typed text; checked against `RANGES.dimensions`. */
  dimensions: string;
  query_prefix: string;
  document_prefix: string;
}

/** What the person did with the saved key: left it, is typing another, or marked it to be removed. */
export interface KeyEdit {
  mode: "saved" | "typing" | "removing";
  typed: string;
}

export const keyEditOf = (hasKey: boolean): KeyEdit => ({ mode: hasKey ? "saved" : "typing", typed: "" });

/** The `api_key` to send: only a typed key, or "" to remove; undefined leaves the stored one alone. */
export function keyToSend(edit: KeyEdit): string | undefined {
  if (edit.mode === "removing") return "";
  if (edit.mode === "typing" && edit.typed.trim() !== "") return edit.typed.trim();
  return undefined;
}

export function embeddingFormOf(saved: EmbeddingSettings): EmbeddingForm {
  const { base_url, model, dimensions, query_prefix, document_prefix } = saved;
  return { base_url, model, dimensions: String(dimensions), query_prefix, document_prefix };
}

export type EmbeddingProblems = Problems<"base_url" | "model" | "dimensions">;

export function embeddingProblems(form: EmbeddingForm): EmbeddingProblems {
  return {
    base_url: urlProblem(form.base_url, "Địa chỉ", false) ?? undefined,
    model: form.model.trim() === "" ? "Model: nhập tên model." : undefined,
    dimensions: numberProblem(form.dimensions, RANGES.dimensions) ?? undefined,
  };
}

/** The patch of an embedding save, or null when nothing changed. */
export function embeddingChange(form: EmbeddingForm, saved: EmbeddingSettings, key: KeyEdit): SettingsPatch | null {
  const clean: EmbeddingForm = {
    ...form,
    base_url: form.base_url.trim(),
    model: form.model.trim(),
    dimensions: String(parseNumber(form.dimensions) ?? form.dimensions),
  };
  const { dimensions, ...rest } = changed(embeddingFormOf(saved), clean);
  const apiKey = keyToSend(key);
  const embedding: NonNullable<SettingsPatch["embedding"]> = {
    ...rest,
    ...(dimensions === undefined ? {} : { dimensions: Number(dimensions) }),
    ...(apiKey === undefined ? {} : { api_key: apiKey }),
  };
  return isEmpty(embedding) ? null : { embedding };
}

export function embeddingState(saved: EmbeddingSettings): string {
  const model = saved.model || "chưa chọn model";
  if (saved.chunks_without_vector === 0) return `Đang dùng ${model}. Mọi đoạn đều đã có vector.`;
  return `Đang dùng ${model}. ${saved.chunks_without_vector} đoạn chưa có vector, nên chỉ tìm bằng từ khóa cho các đoạn đó.`;
}

export function reembedWarning(saved: EmbeddingSettings): string {
  return `Mọi đoạn của kho sẽ được nhúng lại bằng ${saved.model || "model đã lưu"}. Việc chạy nền và tốn phí gọi embedding; trong lúc đó các đoạn chưa có vector mới chỉ được tìm bằng từ khóa.`;
}

export function reembedDone(queued: number): string {
  return queued === 0 ? "Không có đoạn nào cần nhúng lại." : `Đã đưa ${queued} đoạn vào hàng đợi nhúng lại.`;
}

function normalisedText(normalised: boolean | null): string {
  if (normalised === null) return "";
  return normalised ? "đã chuẩn hóa" : "chưa chuẩn hóa";
}

/** The sentence under "Kiểm tra kết nối": the result, and a warning when the dimensions differ from the setting. */
export function embeddingTestText(test: EmbeddingTest, savedDimensions: number): string {
  if (!test.ok) return test.message || "Không kết nối được.";
  const parts = [
    test.message || "Kết nối tốt",
    test.dimensions === null ? "" : `${test.dimensions} chiều`,
    normalisedText(test.normalised),
    test.ms === null ? "" : `${test.ms} ms`,
  ].filter((part) => part !== "");
  const differs = test.dimensions !== null && test.dimensions !== savedDimensions;
  const warn = differs ? ` Số chiều trả về khác số chiều đã lưu (${savedDimensions}): sửa lại rồi nhúng lại toàn bộ.` : "";
  return `${parts.join(" · ")}.${warn}`;
}

// -- judging (Jev) ---------------------------------------------------------------------------------------

export type JudgingForm = KnowledgeSettings["judging"];

export const LEVEL_OPTIONS: readonly { value: JudgeLevel; label: string }[] = [
  { value: "strict", label: "Chặt: từ chối khi đoạn tốt nhất cũng chưa thật chắc" },
  { value: "medium", label: "Vừa (đề xuất)" },
  { value: "loose", label: "Rộng: chỉ từ chối khi gần như không đoạn nào có căn cứ" },
];

const LEVEL_BY_VALUE: Record<string, JudgeLevel> = { strict: "strict", medium: "medium", loose: "loose" };

/** The level a select value names; "medium" for anything else. */
export const asLevel = (value: string): JudgeLevel => LEVEL_BY_VALUE[value] ?? "medium";

export function judgingChange(form: JudgingForm, saved: JudgingForm): SettingsPatch | null {
  const judging = changed(saved, form);
  return isEmpty(judging) ? null : { judging };
}

const JEV_OFF = "Plugin Jev đang tắt: bật plugin Jev trước, rồi nhập khóa TypeSafe ở trang Jev.";
const JEV_NO_KEY =
  "Chưa có khóa TypeSafe: nhập khóa ở trang Jev. Cho tới lúc đó tìm kiếm vẫn chạy, chỉ là chưa được lọc.";

/** What is missing before the judge can work; null when nothing is (or while the state is not known yet). */
export function jevNotice(state: JevState | null): string | null {
  if (state === null) return null;
  if (!state.on) return JEV_OFF;
  return state.hasKey ? null : JEV_NO_KEY;
}

// -- search ----------------------------------------------------------------------------------------------

export interface SearchForm {
  results: string;
  min_score: string;
  char_budget: string;
}

export function searchFormOf(saved: KnowledgeSettings["search"]): SearchForm {
  const { results, min_score, char_budget } = saved;
  return { results: String(results), min_score: String(min_score), char_budget: String(char_budget) };
}

export type SearchProblems = Problems<"results" | "min_score" | "char_budget">;

export function searchProblems(form: SearchForm): SearchProblems {
  return {
    results: numberProblem(form.results, RANGES.results) ?? undefined,
    min_score: numberProblem(form.min_score, RANGES.min_score) ?? undefined,
    char_budget: numberProblem(form.char_budget, RANGES.char_budget) ?? undefined,
  };
}

export function searchChange(form: SearchForm, saved: KnowledgeSettings["search"]): SettingsPatch | null {
  const next: KnowledgeSettings["search"] = {
    ...saved,
    results: parseNumber(form.results) ?? saved.results,
    min_score: parseNumber(form.min_score) ?? saved.min_score,
    char_budget: parseNumber(form.char_budget) ?? saved.char_budget,
  };
  const search = changed(saved, next);
  return isEmpty(search) ? null : { search };
}

// -- benchmark -------------------------------------------------------------------------------------------

export const BENCHMARK_NOTICE =
  "Chế độ này cho phép nạp tài liệu thử thách (giá cũ, bản nháp, tài liệu tấn công thử) để chạy bộ đo. Phải để tắt khi dùng bình thường: tài liệu thử thách không bao giờ được vào kho thật.";
