/** The model the agent talks to and its API key (stored encrypted; shown masked). Applies to the next call. */
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../lib/api";
import { Badge, Button, Card, Field, Input, Notice, PageHeader, Select } from "../ui/kit";

interface ModelShown {
  provider: string;
  model: string;
  base_url: string | null;
  reasoning: string | null;
  dialect: string | null;
  api_key: string;
  api_key_broken: boolean;
  sources: Record<string, "db" | "profile" | "unset">;
}

interface TestOutcome {
  ok: boolean;
  model: string;
  latency_ms?: number;
  error_kind?: string;
}

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
const TEST_ERRORS: Record<string, string> = {
  auth: "Khóa API sai hoặc hết hạn",
  rate_limit: "Nhà cung cấp đang giới hạn số lần gọi",
  transient: "Nhà cung cấp tạm lỗi, thử lại sau",
  config: "Thiếu model hoặc khóa API",
  timeout: "Quá thời gian chờ",
};

interface Form {
  provider: string;
  model: string;
  base_url: string;
  reasoning: string;
  dialect: string;
  api_key: string;
}

function isOutcome(value: unknown): value is TestOutcome {
  return typeof value === "object" && value !== null && "ok" in value && "model" in value;
}

function formOf(shown: ModelShown): Form {
  return {
    provider: shown.provider,
    model: shown.model,
    base_url: shown.base_url ?? "",
    reasoning: shown.reasoning ?? "",
    dialect: shown.dialect ?? "",
    api_key: "",
  };
}

export function ModelPage() {
  const [shown, setShown] = useState<ModelShown | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [notice, setNotice] = useState<{ tone: "success" | "danger" | "info"; text: string } | null>(null);
  const [busy, setBusy] = useState("");

  const show = useCallback((next: ModelShown) => {
    setShown(next);
    setForm(formOf(next));
  }, []);

  useEffect(() => {
    api
      .get<ModelShown>("/v1/admin/model")
      .then(show)
      .catch((err: unknown) => setNotice({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" }));
  }, [show]);

  async function run(label: string, work: () => Promise<void>) {
    setBusy(label);
    setNotice(null);
    try {
      await work();
    } catch (err) {
      setNotice({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" });
    } finally {
      setBusy("");
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    if (!form || !shown) return;
    void run("save", async () => {
      const changes: Record<string, string | null> = {};
      for (const key of ["provider", "model", "base_url", "reasoning", "dialect"] as const) {
        const before = key === "provider" || key === "model" ? shown[key] : (shown[key] ?? "");
        if (form[key] !== before) changes[key] = form[key] === "" ? null : form[key];
      }
      if (form.api_key) changes.api_key = form.api_key;
      show(await api.patch<ModelShown>("/v1/admin/model", changes));
      setNotice({ tone: "success", text: "Đã lưu - áp dụng từ lượt trả lời tiếp theo." });
    });
  }

  const test = () =>
    run("test", async () => {
      // A failed call answers 502 with the outcome in the body.
      const outcome = await api.post<TestOutcome>("/v1/admin/model/test").catch((err: unknown) => {
        if (err instanceof ApiError && isOutcome(err.payload)) return err.payload;
        throw err;
      });
      setNotice(
        outcome.ok
          ? { tone: "success", text: `${outcome.model} trả lời sau ${outcome.latency_ms ?? "?"} ms.` }
          : { tone: "danger", text: TEST_ERRORS[outcome.error_kind ?? ""] ?? `Lỗi: ${outcome.error_kind}` },
      );
    });

  const removeKey = () =>
    run("key", async () => {
      show(await api.patch<ModelShown>("/v1/admin/model", { api_key: null }));
    });

  const reset = () =>
    run("reset", async () => {
      show(await api.del<ModelShown>("/v1/admin/model"));
      setNotice({ tone: "info", text: "Đã xóa mọi cài đặt đã lưu: dùng lại cấu hình của profile." });
    });

  if (!form || !shown) {
    return (
      <div>
        <PageHeader title="Model" />
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
      </div>
    );
  }
  const set = (key: keyof Form) => (value: string) => setForm({ ...form, [key]: value });
  const source = (key: string) => (shown.sources[key] === "db" ? "đã lưu" : "theo profile");

  return (
    <div>
      <PageHeader title="Model" subtitle="Nhà cung cấp, model và khóa API mà agent dùng để trả lời" />
      <form onSubmit={save} className="space-y-4">
        <Card title="Cấu hình">
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Nhà cung cấp" hint={source("provider")}>
              <Select options={PROVIDERS} value={form.provider} onChange={(e) => set("provider")(e.target.value)} />
            </Field>
            <Field label="Model" hint={source("model")}>
              <Input required value={form.model} placeholder="vd: deepseek-chat" onChange={(e) => set("model")(e.target.value)} />
            </Field>
            <Field label="Địa chỉ API (base URL)" hint={`${source("base_url")} - để trống dùng mặc định của nhà cung cấp`}>
              <Input
                type="url"
                value={form.base_url}
                placeholder="https://api.deepseek.com/v1"
                onChange={(e) => set("base_url")(e.target.value)}
              />
            </Field>
            <Field label="Mức suy nghĩ" hint={source("reasoning")}>
              <Select options={REASONING} value={form.reasoning} onChange={(e) => set("reasoning")(e.target.value)} />
            </Field>
            <Field label="Kiểu API (OpenAI-compatible)" hint={source("dialect")}>
              <Select options={DIALECTS} value={form.dialect} onChange={(e) => set("dialect")(e.target.value)} />
            </Field>
          </div>
        </Card>
        <Card
          title="Khóa API"
          aside={
            shown.api_key_broken ? (
              <Badge tone="danger">Khóa đã lưu không đọc được</Badge>
            ) : shown.sources.api_key === "db" ? (
              <Badge tone="success">Đã có khóa: {shown.api_key}</Badge>
            ) : (
              <Badge tone="warning">Chưa có khóa</Badge>
            )
          }
        >
          <Field label="Khóa mới" hint="Để trống để giữ khóa đang có. Khóa được mã hóa và không bao giờ hiện lại.">
            <Input
              type="password"
              autoComplete="off"
              value={form.api_key}
              onChange={(e) => set("api_key")(e.target.value)}
            />
          </Field>
          {shown.sources.api_key === "db" && (
            <Button variant="ghost" className="mt-2" busy={busy === "key"} onClick={removeKey}>
              Xóa khóa đã lưu
            </Button>
          )}
        </Card>
        {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" busy={busy === "save"}>
            Lưu
          </Button>
          <Button variant="secondary" busy={busy === "test"} onClick={test}>
            Gọi thử
          </Button>
          <Button variant="danger" busy={busy === "reset"} onClick={reset}>
            Về cấu hình profile
          </Button>
        </div>
      </form>
    </div>
  );
}
