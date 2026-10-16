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
] as const;
export type ScalarField = (typeof SCALAR_FIELDS)[number];
export type SettingField = ScalarField | "variables";

export const MEMORY_MIN_CHARS = 100;
export const MEMORY_MAX_CHARS = 20000;
const VARIABLE_NAME = /^[a-z][a-z0-9_]{0,63}$/;

export interface AgentSettings {
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

export interface SettingsDraft {
  timezone: string;
  failure_reply: string;
  persona: string;
  rules: string;
  memory_enabled: boolean;
  memory_agent_chars: string;
  memory_user_chars: string;
  variables: VariableRow[];
}

export type SettingsPatch = Partial<Record<ScalarField, string | number | boolean | null>> & {
  variables?: Record<string, string | null> | null;
};

export function isAgentSettings(value: unknown): value is AgentSettings {
  if (typeof value !== "object" || value === null) return false;
  return "timezone" in value && "variables" in value && "sources" in value && "persona" in value;
}

export function draftOf(shown: AgentSettings): SettingsDraft {
  return {
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

/** Only what differs from the shown settings; empty when nothing changed. */
export function patchOf(draft: SettingsDraft, shown: AgentSettings): SettingsPatch {
  const text = (["timezone", "failure_reply", "persona", "rules"] as const)
    .filter((field) => draft[field] !== shown[field])
    .map((field) => [field, draft[field]]);
  const numbers = (["memory_agent_chars", "memory_user_chars"] as const)
    .filter((field) => Number(draft[field]) !== shown[field])
    .map((field) => [field, Number(draft[field])]);
  const memory =
    draft.memory_enabled === shown.memory_enabled ? [] : [["memory_enabled", draft.memory_enabled]];
  const variables = variableChanges(draft, shown);
  const withVariables = Object.keys(variables).length > 0 ? [["variables", variables]] : [];
  return Object.fromEntries([...text, ...numbers, ...memory, ...withVariables]);
}

function memoryError(value: string): string | null {
  const number = Number(value);
  if (value.trim() === "" || !Number.isInteger(number)) return "Nhập một số nguyên";
  if (number < MEMORY_MIN_CHARS || number > MEMORY_MAX_CHARS) {
    return `Trong khoảng ${MEMORY_MIN_CHARS} - ${MEMORY_MAX_CHARS}`;
  }
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
