"use client";

// Add or change one model of the agent's list: ready presets (a click fills the provider, address and model; the
// button of the chosen one stays coloured), the fields, and the model field that offers the provider's own list
// while still taking any name typed by hand. Nothing is stored until the form is saved.
import { type FormEvent, useState } from "react";

import { ApiError, agentApi as api } from "@/lib/agent/api";
import {
  brandOf,
  ENTRIES_PATH,
  entryPath,
  type ModelEntry,
  nextLabel,
} from "@/lib/agent/model-entries";
import { MODEL_PRESETS, type ModelPreset, withPreset } from "@/lib/agent/model-presets";
import {
  Button,
  Card,
  Field,
  Input,
  Notice,
  Select,
  type KitTone,
} from "@/components/agent/plugin-kit";

const PROVIDERS = [
  { value: "openai-compatible", label: "OpenAI-compatible (OpenAI, DeepSeek, OpenRouter...)" },
  { value: "anthropic", label: "Anthropic" },
];
const REASONING = [
  { value: "", label: "Mặc định của nhà cung cấp" },
  { value: "off", label: "Tắt" },
  { value: "low", label: "Thấp" },
  { value: "medium", label: "Vừa" },
  { value: "high", label: "Cao" },
];
const DIALECTS = [
  { value: "", label: "Tự đoán theo địa chỉ" },
  { value: "openai", label: "OpenAI" },
  { value: "deepseek", label: "DeepSeek" },
];
const ERRORS: Record<string, string> = {
  auth: "Khóa API sai hoặc hết hạn",
  rate_limit: "Nhà cung cấp đang giới hạn số lần gọi",
  transient: "Nhà cung cấp tạm lỗi, thử lại sau",
  config: "Thiếu model hoặc khóa API",
  timeout: "Quá thời gian chờ",
};
const KEY_FIELD = "model-api-key";
const MODEL_OPTIONS = "model-options";
const NO_ENDPOINT = "Nhà cung cấp không cho xem danh sách";

interface Form {
  label: string;
  provider: string;
  model: string;
  base_url: string;
  reasoning: string;
  dialect: string;
  api_key: string;
}

interface ModelListing {
  ok: boolean;
  models: string[];
  error_kind?: string;
}

type Message = { tone: KitTone; text: string };

const EMPTY_FORM: Form = {
  label: "",
  provider: "openai-compatible",
  model: "",
  base_url: "",
  reasoning: "",
  dialect: "",
  api_key: "",
};

const CHANGEABLE = ["label", "provider", "model", "base_url", "reasoning", "dialect"] as const;

function isListing(value: unknown): value is ModelListing {
  return typeof value === "object" && value !== null && "models" in value && "ok" in value;
}

function formOf(entry: ModelEntry | null): Form {
  if (!entry) return EMPTY_FORM;
  return {
    label: entry.label,
    provider: entry.provider,
    model: entry.model,
    base_url: entry.base_url ?? "",
    reasoning: entry.reasoning ?? "",
    dialect: entry.dialect ?? "",
    api_key: "",
  };
}

const orNull = (value: string) => (value === "" ? null : value);

/** What a new model sends: an empty address, effort or API kind is left out, the agent decides. */
function newBody(form: Form): Record<string, string> {
  const optional = (["base_url", "reasoning", "dialect", "api_key"] as const)
    .filter((key) => form[key] !== "")
    .map((key) => [key, form[key]]);
  return {
    label: form.label.trim(),
    provider: form.provider,
    model: form.model.trim(),
    ...Object.fromEntries(optional),
  };
}

/** What an edit sends: only the fields that changed; the key only when one was typed. */
function changesOf(form: Form, entry: ModelEntry): Record<string, string | null> {
  const before = formOf(entry);
  const changed = CHANGEABLE.filter((key) => form[key] !== before[key]).map((key) => [
    key,
    orNull(form[key]),
  ]);
  const key = form.api_key ? [["api_key", form.api_key]] : [];
  return Object.fromEntries([...changed, ...key]);
}

export function ModelEntryForm({
  editing,
  entries,
  onSaved,
  onCancel,
}: {
  editing: ModelEntry | null;
  entries: readonly ModelEntry[];
  onSaved: (text: string) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<Form>(() => formOf(editing));
  const [preset, setPreset] = useState<ModelPreset | null>(null);
  const [labelTyped, setLabelTyped] = useState(editing !== null);
  const [models, setModels] = useState<string[]>([]);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState("");

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    setMessage(null);
    try {
      await work();
    } catch (err) {
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" });
    } finally {
      setBusy("");
    }
  }

  const set = (key: keyof Form) => (value: string) => setForm({ ...form, [key]: value });

  function applyPreset(chosen: ModelPreset) {
    const filled = withPreset(form, chosen);
    const label = labelTyped ? form.label : nextLabel(chosen.label, entries);
    setForm({ ...filled, label });
    setPreset(chosen);
    setModels([]);
    setMessage({
      tone: "info",
      text: chosen.keyUrl
        ? `Đã điền mẫu ${chosen.label}. Dán khóa API rồi bấm Thêm vào danh sách.`
        : `Đã điền mẫu ${chosen.label}. Chọn model rồi bấm Thêm vào danh sách.`,
    });
    document.getElementById(KEY_FIELD)?.focus();
  }

  function save(event: FormEvent) {
    event.preventDefault();
    void run("save", async () => {
      if (editing) {
        await api.patch(entryPath(editing.id), changesOf(form, editing));
        onSaved(`Đã lưu ${form.label.trim()}.`);
        return;
      }
      await api.post(ENTRIES_PATH, newBody(form));
      onSaved(`Đã thêm ${form.label.trim()} vào danh sách.`);
    });
  }

  const listModels = () =>
    run("list", async () => {
      const typed = { provider: form.provider, base_url: form.base_url, api_key: form.api_key };
      const trying = Object.fromEntries(Object.entries(typed).filter(([, value]) => value !== ""));
      const body = editing ? { ...trying, entry_id: editing.id } : trying;
      // A refusal answers 502 with the error kind in the body.
      const listing = await api
        .post<ModelListing>("/v1/admin/model/list", body)
        .catch((err: unknown) => {
          if (err instanceof ApiError && isListing(err.payload)) return err.payload;
          throw err;
        });
      setModels(listing.models);
      if (!listing.ok) {
        const why = ERRORS[listing.error_kind ?? ""] ?? NO_ENDPOINT;
        setMessage({ tone: "danger", text: `${why}. Vẫn gõ tên model tay được.` });
        return;
      }
      setMessage({
        tone: "info",
        text:
          listing.models.length > 0
            ? `Có ${listing.models.length} model: chọn trong ô Model hoặc gõ tay.`
            : "Nhà cung cấp không trả model nào: gõ tên model tay.",
      });
    });

  const brand = brandOf({ provider: form.provider, base_url: form.base_url || null });
  const keyHint = editing?.has_key
    ? "Để trống để giữ khóa đang có. Khóa được mã hóa và không bao giờ hiện lại."
    : "Khóa được mã hóa và không bao giờ hiện lại.";

  return (
    <form onSubmit={save} className="space-y-4">
      {!editing && (
        <Card title="Mẫu có sẵn">
          <p className="mb-3 text-small text-ink-soft">
            Bấm một mẫu để điền sẵn nhà cung cấp, địa chỉ và model; chỉ cần thêm khóa API. Cùng một
            nhà cung cấp thêm được nhiều lần, mỗi lần một khóa.
          </p>
          <div className="flex flex-wrap gap-2">
            {MODEL_PRESETS.map((item) => (
              <Button
                key={item.id}
                variant={preset?.id === item.id ? "primary" : "secondary"}
                aria-pressed={preset?.id === item.id}
                onClick={() => applyPreset(item)}
              >
                {item.label}
              </Button>
            ))}
          </div>
        </Card>
      )}
      <Card title={editing ? `Sửa ${editing.label}` : "Model mới"}>
        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label="Tên trong danh sách"
            hint={`Để phân biệt các khóa ${brand}, vd "DeepSeek công ty".`}
          >
            <Input
              required
              maxLength={100}
              value={form.label}
              placeholder="vd: DeepSeek công ty"
              onChange={(e) => {
                setLabelTyped(true);
                set("label")(e.target.value);
              }}
            />
          </Field>
          <Field label="Nhà cung cấp">
            <Select
              options={PROVIDERS}
              value={form.provider}
              onChange={(e) => set("provider")(e.target.value)}
            />
          </Field>
          <div>
            <Field label="Model">
              <Input
                required
                list={MODEL_OPTIONS}
                value={form.model}
                placeholder="vd: deepseek-chat"
                onChange={(e) => set("model")(e.target.value)}
              />
            </Field>
            <datalist id={MODEL_OPTIONS}>
              {models.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
            <Button variant="ghost" className="mt-1" busy={busy === "list"} onClick={listModels}>
              Lấy danh sách model từ nhà cung cấp
            </Button>
          </div>
          <Field label="Địa chỉ API (base URL)" hint="Để trống dùng mặc định của nhà cung cấp">
            <Input
              type="url"
              value={form.base_url}
              placeholder="https://api.deepseek.com/v1"
              onChange={(e) => set("base_url")(e.target.value)}
            />
          </Field>
          <Field label="Mức suy nghĩ">
            <Select
              options={REASONING}
              value={form.reasoning}
              onChange={(e) => set("reasoning")(e.target.value)}
            />
          </Field>
          <Field label="Kiểu API (OpenAI-compatible)">
            <Select
              options={DIALECTS}
              value={form.dialect}
              onChange={(e) => set("dialect")(e.target.value)}
            />
          </Field>
          <Field label="Khóa API" hint={keyHint}>
            <Input
              id={KEY_FIELD}
              type="password"
              autoComplete="off"
              value={form.api_key}
              onChange={(e) => set("api_key")(e.target.value)}
            />
          </Field>
        </div>
        {preset?.keyUrl && (
          <p className="mt-3 text-small text-ink-soft">
            Lấy khóa {preset.label} ở{" "}
            <a
              href={preset.keyUrl}
              target="_blank"
              rel="noreferrer"
              className="text-link underline underline-offset-2"
            >
              {new URL(preset.keyUrl).host}
            </a>
            .
          </p>
        )}
      </Card>
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" busy={busy === "save"}>
          {editing ? "Lưu thay đổi" : "Thêm vào danh sách"}
        </Button>
        <Button variant="secondary" onClick={onCancel}>
          Hủy
        </Button>
      </div>
    </form>
  );
}
