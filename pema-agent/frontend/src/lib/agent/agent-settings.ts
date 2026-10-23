// The agent's own settings (`/v1/admin/settings`): what the Cài đặt page shows, the draft the admin edits and the
// rule for what a save sends: only the fields that changed (a value sets it, null gives it back to the profile).
export const SETTINGS_PATH = "/v1/admin/settings";

export type FieldSource = "db" | "profile";

export const SCALAR_FIELDS = [
  "timezone",
  "failure_reply",
  "persona",
  "rules",
  "memory_enabled",
  "memory_agent_chars",
  "memory_user_chars",
  "cases_enabled",
  "proactive_per_person_per_day",
  "tokens_per_session_per_day",
  "tokens_per_day",
  "max_steps",
  "max_output_tokens",
  "max_turn_s",
  "max_turn_tokens",
  "stop_after_repeats",
  "error_streak_stop",
  "max_parallel_tools",
  "max_tool_calls_per_step",
  "compact_at",
  "keep_recent_ratio",
] as const;
export type ScalarField = (typeof SCALAR_FIELDS)[number];

/** The numbers the page edits in one way: the cap of the cases, the token budget, the limits of a turn and of
 * compaction (docs/PLAN-case-loop.md 8). The same bounds as the backend's. */
export const NUMBER_FIELDS = [
  "proactive_per_person_per_day",
  "tokens_per_session_per_day",
  "tokens_per_day",
  "max_steps",
  "max_output_tokens",
  "max_turn_s",
  "max_turn_tokens",
  "stop_after_repeats",
  "error_streak_stop",
  "max_parallel_tools",
  "max_tool_calls_per_step",
  "compact_at",
  "keep_recent_ratio",
] as const;
export type NumberField = (typeof NUMBER_FIELDS)[number];

export interface NumberSpec {
  min: number;
  max: number;
  integer: boolean;
  label: string;
  hint: string;
  /** Empty is a value of its own (no limit), not an error. */
  optional?: boolean;
}

export const NUMBER_SPECS: Record<NumberField, NumberSpec> = {
  proactive_per_person_per_day: {
    min: 1,
    max: 20,
    integer: true,
    label: "Tin chủ động tối đa mỗi người mỗi ngày",
    hint: "Tính chung cho mọi ca (nhắc lịch, chăm sóc lại). Hết chỗ thì ca chờ sang ngày.",
  },
  tokens_per_session_per_day: {
    min: 10_000,
    max: 100_000_000,
    integer: true,
    label: "Token tối đa mỗi cuộc chat mỗi ngày",
    hint: "Quá mức này cuộc chat không chạy lượt mới tới hôm sau.",
  },
  tokens_per_day: {
    min: 100_000,
    max: 2_000_000_000,
    integer: true,
    label: "Token tối đa của cả agent mỗi ngày",
    hint: "Quá mức này agent không chạy lượt mới tới hôm sau.",
  },
  max_steps: {
    min: 1,
    max: 50,
    integer: true,
    label: "Số bước tối đa mỗi lượt",
    hint: "Mỗi bước là một lần model nghĩ hoặc gọi tool. Hết bước thì agent trả lời với những gì đã có.",
  },
  max_output_tokens: {
    min: 64,
    max: 32_768,
    integer: true,
    label: "Độ dài trả lời tối đa (token)",
    hint: "Mỗi lần model viết.",
  },
  max_turn_s: {
    min: 10,
    max: 1_800,
    integer: false,
    label: "Thời gian tối đa mỗi lượt (giây)",
    hint: "Quá thời gian thì không bắt đầu bước mới, model trả lời luôn.",
  },
  max_turn_tokens: {
    min: 1_000,
    max: 10_000_000,
    integer: true,
    optional: true,
    label: "Token tối đa mỗi lượt",
    hint: "Để trống: không giới hạn (theo profile).",
  },
  stop_after_repeats: {
    min: 2,
    max: 50,
    integer: true,
    label: "Dừng khi gọi cùng một tool liền bấy nhiêu lần",
    hint: "Phải lớn hơn mốc nhắc lặp cuối của profile (mặc định 8).",
  },
  error_streak_stop: {
    min: 2,
    max: 50,
    integer: true,
    label: "Dừng khi tool lỗi liền bấy nhiêu lần",
    hint: "Phải lớn hơn mốc nhắc lỗi của profile (mặc định 3).",
  },
  max_parallel_tools: {
    min: 1,
    max: 32,
    integer: true,
    label: "Tool chạy song song tối đa",
    hint: "",
  },
  max_tool_calls_per_step: {
    min: 1,
    max: 64,
    integer: true,
    label: "Lần gọi tool tối đa mỗi bước",
    hint: "",
  },
  compact_at: {
    min: 0.3,
    max: 0.95,
    integer: false,
    label: "Nén khi hội thoại dùng tới (tỉ lệ cửa sổ)",
    hint: "Ví dụ 0.75: nén khi đã dùng 75% cửa sổ ngữ cảnh của model.",
  },
  keep_recent_ratio: {
    min: 0,
    max: 0.6,
    integer: false,
    label: "Phần mới nhất giữ nguyên khi nén (tỉ lệ)",
    hint: "Ví dụ 0.2: giữ nguyên chữ phần hội thoại mới nhất, khoảng 20% ngưỡng nén; phần cũ hơn được tóm tắt.",
  },
};
export type SettingField = ScalarField | "variables";

export const MEMORY_MIN_CHARS = 100;
export const MEMORY_MAX_CHARS = 20000;
const VARIABLE_NAME = /^[a-z][a-z0-9_]{0,63}$/;

export interface AgentSettings extends Record<NumberField, number | null> {
  timezone: string;
  failure_reply: string;
  /** Effective values of the variables (the profile's, with the stored ones laid over). */
  variables: Record<string, string>;
  /** The text with its `{{variable}}` placeholders. */
  persona: string;
  rules: string;
  memory_enabled: boolean;
  memory_agent_chars: number;
  memory_user_chars: number;
  cases_enabled: boolean;
  sources: Record<SettingField, FieldSource>;
  stored: boolean;
  version: number;
  updated_by: string | null;
}

export interface VariableRow {
  name: string;
  value: string;
  /** Typed in this session: its name is still free to edit. */
  isNew: boolean;
}

export interface SettingsDraft extends Record<NumberField, string> {
  timezone: string;
  failure_reply: string;
  persona: string;
  rules: string;
  memory_enabled: boolean;
  memory_agent_chars: string;
  memory_user_chars: string;
  cases_enabled: boolean;
  variables: VariableRow[];
}

export type SettingsPatch = Partial<Record<ScalarField, string | number | boolean | null>> & {
  variables?: Record<string, string | null> | null;
};

export function isAgentSettings(value: unknown): value is AgentSettings {
  if (typeof value !== "object" || value === null) return false;
  return "timezone" in value && "variables" in value && "sources" in value && "persona" in value;
}

function numbersOf(shown: AgentSettings): Record<NumberField, string> {
  const entries = NUMBER_FIELDS.map((field) => [
    field,
    shown[field] === null ? "" : String(shown[field]),
  ]);
  // Object.fromEntries loses the keys' type; the entries are exactly NUMBER_FIELDS.
  return Object.fromEntries(entries) as Record<NumberField, string>;
}

export function draftOf(shown: AgentSettings): SettingsDraft {
  return {
    ...numbersOf(shown),
    cases_enabled: shown.cases_enabled,
    timezone: shown.timezone,
    failure_reply: shown.failure_reply,
    persona: shown.persona,
    rules: shown.rules,
    memory_enabled: shown.memory_enabled,
    memory_agent_chars: String(shown.memory_agent_chars),
    memory_user_chars: String(shown.memory_user_chars),
    variables: Object.entries(shown.variables).map(([name, value]) => ({
      name,
      value,
      isNew: false,
    })),
  };
}

/** The draft with only `fields` taken from a fresh answer: what the admin typed elsewhere stays. */
export function takeFields(
  draft: SettingsDraft,
  fresh: AgentSettings,
  fields: readonly SettingField[],
): SettingsDraft {
  const next = draftOf(fresh);
  const taken = fields.map((field) => [field, next[field]]);
  return { ...draft, ...Object.fromEntries(taken) };
}

const isBlankNew = (row: VariableRow) => row.isNew && row.name === "" && row.value === "";

function variableChanges(draft: SettingsDraft, shown: AgentSettings): Record<string, string> {
  const changed = draft.variables
    .filter((row) => !isBlankNew(row))
    .filter((row) => row.isNew || shown.variables[row.name] !== row.value)
    .map((row) => [row.name, row.value]);
  return Object.fromEntries(changed);
}

const numberOrNull = (value: string) => (value.trim() === "" ? null : Number(value));

function numberChanged(draft: SettingsDraft, shown: AgentSettings, field: NumberField): boolean {
  return numberOrNull(draft[field]) !== shown[field];
}

/** Only what differs from the shown settings; empty when nothing changed. */
export function patchOf(draft: SettingsDraft, shown: AgentSettings): SettingsPatch {
  const text = (["timezone", "failure_reply", "persona", "rules"] as const)
    .filter((field) => draft[field] !== shown[field])
    .map((field) => [field, draft[field]]);
  const numbers = (["memory_agent_chars", "memory_user_chars"] as const)
    .filter((field) => Number(draft[field]) !== shown[field])
    .map((field) => [field, Number(draft[field])]);
  const limits = NUMBER_FIELDS.filter((field) => numberChanged(draft, shown, field)).map(
    (field) => [field, numberOrNull(draft[field])],
  );
  const memory =
    draft.memory_enabled === shown.memory_enabled ? [] : [["memory_enabled", draft.memory_enabled]];
  const cases =
    draft.cases_enabled === shown.cases_enabled ? [] : [["cases_enabled", draft.cases_enabled]];
  const variables = variableChanges(draft, shown);
  const withVariables = Object.keys(variables).length > 0 ? [["variables", variables]] : [];
  return Object.fromEntries([
    ...text,
    ...numbers,
    ...limits,
    ...memory,
    ...cases,
    ...withVariables,
  ]);
}

function memoryError(value: string): string | null {
  const number = Number(value);
  if (value.trim() === "" || !Number.isInteger(number)) return "Nhập một số nguyên";
  if (number < MEMORY_MIN_CHARS || number > MEMORY_MAX_CHARS) {
    return `Trong khoảng ${MEMORY_MIN_CHARS} - ${MEMORY_MAX_CHARS}`;
  }
  return null;
}

export function numberError(field: NumberField, value: string): string | null {
  const spec = NUMBER_SPECS[field];
  if (value.trim() === "") return spec.optional ? null : "Nhập một số";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Nhập một số";
  if (spec.integer && !Number.isInteger(number)) return "Nhập một số nguyên";
  if (number < spec.min || number > spec.max) return `Trong khoảng ${spec.min} - ${spec.max}`;
  return null;
}

function variableError(row: VariableRow, rows: readonly VariableRow[]): string | null {
  if (!VARIABLE_NAME.test(row.name)) return "Tên biến: chữ thường, số và _, bắt đầu bằng chữ";
  if (rows.filter((other) => other.name === row.name).length > 1) return "Tên biến bị trùng";
  if (row.value.trim() === "" || row.value.length > 500) return "Giá trị từ 1 đến 500 ký tự";
  return null;
}

/** What the page refuses before sending, by field; the server checks again. */
export function draftErrors(draft: SettingsDraft): Partial<Record<SettingField, string>> {
  const found: [SettingField, string | null][] = [
    ["timezone", draft.timezone.trim() === "" ? "Nhập múi giờ, ví dụ Asia/Ho_Chi_Minh" : null],
    ["memory_agent_chars", memoryError(draft.memory_agent_chars)],
    ["memory_user_chars", memoryError(draft.memory_user_chars)],
    ...NUMBER_FIELDS.map((field): [SettingField, string | null] => [
      field,
      numberError(field, draft[field]),
    ]),
    [
      "variables",
      draft.variables
        .filter((row) => !isBlankNew(row))
        .map((row) => variableError(row, draft.variables))
        .find((error) => error !== null) ?? null,
    ],
  ];
  return Object.fromEntries(found.filter(([, error]) => error !== null));
}

export const isStored = (shown: AgentSettings, field: SettingField) =>
  shown.sources[field] === "db";
