// The fake agent's own settings and tool switches (`/v1/admin/settings`, `/v1/admin/tools`), kept in memory the way
// the backend keeps them in its table: a value sets a field and flips its source to "db", null gives it back to the
// profile, `variables` holds only the values an admin changed. FICTIONAL profile. Not in the clinic contract.
import { NUMBER_FIELDS, NUMBER_SPECS } from "../src/lib/agent/agent-settings";
import { type Reply, type Router, bodyOf } from "./core";

const PROFILE = {
  timezone: "Asia/Ho_Chi_Minh",
  failure_reply: "Xin lỗi, hệ thống đang bận. Nhân viên sẽ liên hệ lại với bạn sớm.",
  variables: { clinic_name: "Phòng khám Pema (dữ liệu mẫu)", tone: "lịch sự, ngắn gọn" } as Record<
    string,
    string
  >,
  persona: "Bạn là trợ lý của {{clinic_name}}. Luôn trả lời {{tone}}.",
  rules: "Không chẩn đoán bệnh. Chuyển câu hỏi y khoa cho bác sĩ của {{clinic_name}}.",
  memory_enabled: true,
  memory_agent_chars: 2200,
  memory_user_chars: 1400,
  cases_enabled: false,
  proactive_per_person_per_day: 2,
  tokens_per_session_per_day: 2_000_000,
  tokens_per_day: 50_000_000,
  max_steps: 10,
  max_output_tokens: 2048,
  max_turn_s: 300,
  max_turn_tokens: null as number | null,
  stop_after_repeats: 10,
  error_streak_stop: 5,
  max_parallel_tools: 4,
  max_tool_calls_per_step: 8,
  compact_at: 0.75,
  keep_recent_ratio: 0.2,
};

type Scalars = Omit<typeof PROFILE, "variables">;
type Stored = {
  scalars: Partial<Scalars>;
  variables: Record<string, string>;
  tools: Record<string, boolean>;
  version: number;
  updated_by: string | null;
};

const TOOLS = [
  {
    name: "get_datetime",
    description: "Current date and time in the agent's time zone.",
    source: "core",
    default: true,
  },
  {
    name: "web_fetch",
    description: "Fetch a web page and read its text.",
    source: "core",
    default: false,
  },
  {
    name: "kb_search",
    description: "Search the knowledge store for approved clinic documents.",
    source: "plugin",
    default: true,
  },
  {
    name: "skill_write",
    description: "Save a reusable skill the agent learned from a conversation.",
    source: "plugin",
    default: true,
  },
  {
    name: "zalo_send_message",
    description: "Send a message through a clinic Zalo account.",
    source: "plugin",
    default: true,
  },
] as const;
const MEMORY_TOOL = {
  name: "memory",
  description: "Read and write the agent's notes about itself and about the customer.",
  source: "core",
} as const;

const ADMIN = "owner@pema.test";
const FILLED = /\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g;
const VARIABLE_NAME = /^[a-z][a-z0-9_]{0,63}$/;
const SCALAR_NAMES = [...Object.keys(PROFILE).filter((name) => name !== "variables")];

let stored = emptyStored();

function emptyStored(): Stored {
  return { scalars: {}, variables: {}, tools: {}, version: 0, updated_by: null };
}

const refuse = (status: number, kind: string, message: string): Reply => ({
  status,
  body: { error: { kind, message } },
});

const variablesOf = (from: Stored) => ({ ...PROFILE.variables, ...from.variables });
const isEmpty = (from: Stored) =>
  Object.keys(from.scalars).length +
    Object.keys(from.variables).length +
    Object.keys(from.tools).length ===
  0;

function show() {
  const scalars = { ...PROFILE, ...stored.scalars };
  const source = (name: string) => (name in stored.scalars ? "db" : "profile");
  return {
    ...scalars,
    variables: variablesOf(stored),
    sources: {
      ...Object.fromEntries(SCALAR_NAMES.map((name) => [name, source(name)])),
      variables: Object.keys(stored.variables).length > 0 ? "db" : "profile",
    },
    stored: !isEmpty(stored),
    version: stored.version,
    updated_by: stored.updated_by,
  };
}

function toolList() {
  const memoryOn = stored.scalars.memory_enabled ?? PROFILE.memory_enabled;
  const rows = TOOLS.map((tool) => ({
    ...tool,
    enabled: stored.tools[tool.name] ?? tool.default,
    stored: tool.name in stored.tools,
  }));
  const memory = {
    ...MEMORY_TOOL,
    enabled: memoryOn,
    default: PROFILE.memory_enabled,
    stored: "memory_enabled" in stored.scalars,
  };
  // Core tools, then the memory tool, then the plugins' tools: the backend's order.
  const core = rows.filter((row) => row.source === "core");
  return {
    tools: [...core, memory, ...rows.filter((row) => row.source === "plugin")],
    version: stored.version,
  };
}

/** The first reason the change is refused, or null; the same limits as the backend. */
function problemOf(next: Stored): string | null {
  const scalars = { ...PROFILE, ...next.scalars };
  const names = Object.keys(next.variables);
  const badName = names.find((name) => !VARIABLE_NAME.test(name));
  if (badName) return `variable name '${badName}': use a-z, 0-9 and '_'`;
  const badValue = names.find(
    (name) => next.variables[name].length < 1 || next.variables[name].length > 500,
  );
  if (badValue) return `variable ${badValue}: 1 to 500 characters`;
  if (Object.keys(variablesOf(next)).length > 50) return "at most 50 variables";
  if (!validZone(scalars.timezone)) return `unknown time zone '${scalars.timezone}'`;
  if (scalars.failure_reply.length > 1000) return "the reply holds at most 1000 characters";
  const memory = [scalars.memory_agent_chars, scalars.memory_user_chars];
  if (memory.some((n) => !Number.isInteger(n) || n < 100 || n > 20000)) {
    return "memory_agent_chars is between 100 and 20000";
  }
  const outside = NUMBER_FIELDS.find((name) => !withinSpec(name, next.scalars[name]));
  if (outside)
    return `${outside} is between ${NUMBER_SPECS[outside].min} and ${NUMBER_SPECS[outside].max}`;
  return (
    missingVariable("persona", scalars.persona, next) ??
    missingVariable("rules", scalars.rules, next)
  );
}

function withinSpec(name: (typeof NUMBER_FIELDS)[number], value: unknown): boolean {
  if (value === undefined || value === null) return true;
  const spec = NUMBER_SPECS[name];
  if (typeof value !== "number" || (spec.integer && !Number.isInteger(value))) return false;
  return value >= spec.min && value <= spec.max;
}

function validZone(zone: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: zone });
    return zone !== "";
  } catch {
    return false;
  }
}

function missingVariable(field: string, text: string, next: Stored): string | null {
  if (text.length > 20000) return `the ${field} hold at most 20000 characters`;
  const known = variablesOf(next);
  const missing = [...text.matchAll(FILLED)].map((hit) => hit[1]).find((name) => !(name in known));
  return missing ? `${field} uses {{${missing}}} with no value` : null;
}

function save(next: Stored): Reply {
  const problem = problemOf(next);
  if (problem) return refuse(422, "invalid", problem);
  stored = { ...next, version: stored.version + 1, updated_by: ADMIN };
  return { body: show() };
}

function change(body: Record<string, unknown>): Reply {
  const scalars = { ...stored.scalars };
  SCALAR_NAMES.filter((name) => name in body).forEach((name) => {
    if (body[name] === null) delete scalars[name as keyof Scalars];
    else Object.assign(scalars, { [name]: body[name] });
  });
  return save({ ...stored, scalars, variables: changedVariables(body) });
}

function changedVariables(body: Record<string, unknown>): Record<string, string> {
  if (!("variables" in body)) return stored.variables;
  if (body.variables === null) return {};
  const merged = { ...stored.variables };
  Object.entries(body.variables as Record<string, string | null>).forEach(([name, value]) => {
    if (value === null) delete merged[name];
    else merged[name] = value;
  });
  return merged;
}

function switchTool(name: string, enabled: boolean | null): Reply {
  if (name === MEMORY_TOOL.name) return changeMemory(enabled);
  if (!TOOLS.some((tool) => tool.name === name)) {
    return refuse(404, "unknown_tool", `no tool '${name}' (is its plugin on?)`);
  }
  const tools = { ...stored.tools };
  if (enabled === null) delete tools[name];
  else tools[name] = enabled;
  stored = { ...stored, tools, version: stored.version + 1, updated_by: ADMIN };
  return { body: toolList() };
}

function changeMemory(enabled: boolean | null): Reply {
  const scalars = { ...stored.scalars };
  if (enabled === null) delete scalars.memory_enabled;
  else scalars.memory_enabled = enabled;
  stored = { ...stored, scalars, version: stored.version + 1, updated_by: ADMIN };
  return { body: toolList() };
}

export function registerAgentSettings(r: Router): void {
  r.get("/v1/admin/settings", null, (): Reply => ({ body: show() }));
  r.patch("/v1/admin/settings", null, (ctx): Reply => change(bodyOf<Record<string, unknown>>(ctx)));
  r.delete("/v1/admin/settings", null, (): Reply => {
    stored = { ...emptyStored(), version: stored.version + 1, updated_by: ADMIN };
    return { body: show() };
  });
  r.get("/v1/admin/tools", null, (): Reply => ({ body: toolList() }));
  r.put("/v1/admin/tools/{name}", null, (ctx): Reply => {
    const { enabled } = bodyOf<{ enabled?: boolean | null }>(ctx);
    return switchTool(ctx.params.name, enabled ?? null);
  });
}
