// Ready settings for the usual model providers: a click fills the Model page's form (nothing is saved), the person
// pastes the key. A model name is given only where it is known to be right; elsewhere the list comes from the
// provider's API (`POST /v1/admin/model/list`) and the person picks or types one. Add or change a provider here.

export interface ModelPreset {
  id: string;
  label: string;
  provider: "openai-compatible" | "anthropic";
  /** Empty: the provider's default host. */
  base_url: string;
  /** Empty: pick from the provider's list. */
  model: string;
  /** Only for OpenAI-compatible providers; empty: guessed from the address. */
  dialect: "" | "openai" | "deepseek";
  /** Where the key is made; empty when the provider needs none. */
  keyUrl: string;
}

export const MODEL_PRESETS: readonly ModelPreset[] = [
  {
    id: "deepseek",
    label: "DeepSeek",
    provider: "openai-compatible",
    base_url: "https://api.deepseek.com",
    model: "deepseek-v4-pro",
    dialect: "deepseek",
    keyUrl: "https://platform.deepseek.com/api_keys",
  },
  {
    id: "openai",
    label: "OpenAI",
    provider: "openai-compatible",
    base_url: "https://api.openai.com/v1",
    model: "",
    dialect: "openai",
    keyUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    provider: "anthropic",
    base_url: "",
    model: "claude-sonnet-5-5",
    dialect: "",
    keyUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    provider: "openai-compatible",
    base_url: "https://openrouter.ai/api/v1",
    model: "",
    dialect: "",
    keyUrl: "https://openrouter.ai/keys",
  },
  {
    id: "gemini",
    label: "Gemini",
    provider: "openai-compatible",
    base_url: "https://generativelanguage.googleapis.com/v1beta/openai/",
    model: "",
    dialect: "openai",
    keyUrl: "https://aistudio.google.com/apikey",
  },
  {
    id: "ollama",
    label: "Ollama (máy nội bộ)",
    provider: "openai-compatible",
    base_url: "http://localhost:11434/v1",
    model: "",
    dialect: "openai",
    keyUrl: "",
  },
];

export interface PresetFields {
  provider: string;
  model: string;
  base_url: string;
  reasoning: string;
  dialect: string;
}

/** The form after a preset: its provider, address, model and API kind; the reasoning goes back to the default. */
export function withPreset<T extends PresetFields>(form: T, preset: ModelPreset): T {
  return {
    ...form,
    provider: preset.provider,
    base_url: preset.base_url,
    model: preset.model,
    dialect: preset.dialect,
    reasoning: "",
  };
}
