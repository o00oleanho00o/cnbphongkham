/** "Jev": the TypeSafe key, the model and the token allowance of the day, a connection test and what each day used. */
import { useCallback, useEffect, useState } from "react";

import { jev, messageOf } from "./client";
import {
  type Form,
  capHint,
  formOf,
  formatCount,
  formatUsd,
  hasProblems,
  parseTokens,
  problems,
  settingsChange,
  todayText,
} from "./logic";
import { ui } from "./sdk";
import type { Settings, TestResult, Usage } from "./types";

interface Message {
  tone: "success" | "danger";
  text: string;
}

function KeyCard({ saved, onSaved }: { saved: Settings; onSaved: (next: Settings) => void }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState<Message | null>(null);
  const [tested, setTested] = useState<TestResult | null>(null);
  const found = problems(formOf(saved), typed);

  async function run(name: string, work: () => Promise<Message | null>) {
    setBusy(name);
    setMessage(null);
    try {
      setMessage(await work());
    } catch (err) {
      setMessage({ tone: "danger", text: messageOf(err) });
    } finally {
      setBusy("");
    }
  }

  const save = () =>
    run("save", async () => {
      onSaved(await jev.saveSettings({ api_key: typed.trim() }));
      setTyped("");
      setTested(null);
      return { tone: "success", text: "Đã lưu khóa." };
    });

  const remove = () =>
    run("remove", async () => {
      onSaved(await jev.saveSettings({ api_key: "" }));
      setTested(null);
      return { tone: "success", text: "Đã xóa khóa." };
    });

  const test = () =>
    run("test", async () => {
      setTested(await jev.test());
      return null;
    });

  return (
    <ui.Card
      title="Khóa TypeSafe"
      aside={<ui.Badge tone={saved.has_key ? "success" : "warning"}>{saved.has_key ? "Đã lưu khóa" : "Chưa có khóa"}</ui.Badge>}
    >
      <div className="space-y-3">
        <ui.Field
          label={saved.has_key ? "Khóa mới (để thay khóa đang lưu)" : "Khóa API"}
          hint="Khóa được mã hóa và không bao giờ hiện lại. Lấy khóa ở bảng điều khiển của TypeSafe."
          error={found.key}
        >
          <ui.Input
            type="password"
            autoComplete="off"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </ui.Field>
        <div className="flex flex-wrap gap-2">
          <ui.Button busy={busy === "save"} disabled={typed.trim() === "" || found.key !== undefined} onClick={() => void save()}>
            Lưu khóa
          </ui.Button>
          <ui.Button variant="secondary" busy={busy === "test"} onClick={() => void test()}>
            Kiểm tra kết nối
          </ui.Button>
          {saved.has_key && (
            <ui.Button variant="ghost" busy={busy === "remove"} onClick={() => void remove()}>
              Xóa khóa
            </ui.Button>
          )}
        </div>
        {message && <ui.Notice tone={message.tone}>{message.text}</ui.Notice>}
        {tested && (
          <ui.Notice tone={tested.ok ? "success" : "danger"}>
            {tested.ok && tested.ms !== null ? `${tested.message} ${tested.ms} ms.` : tested.message}
          </ui.Notice>
        )}
        <p className="text-label text-ink-soft">
          Câu tìm và nội dung các đoạn tài liệu được gửi tới TypeSafe (Mỹ) để chấm. Cuộc gọi tính tiền theo token đầu vào.
        </p>
      </div>
    </ui.Card>
  );
}

function SettingsCard({ saved, onSaved }: { saved: Settings; onSaved: (next: Settings) => void }) {
  const [form, setForm] = useState<Form>(() => formOf(saved));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message | null>(null);
  const found = problems(form, "");
  const change = settingsChange(form, saved);
  const shown = (text?: string) => (change ? text : undefined);

  async function save() {
    if (!change || hasProblems(found)) return;
    setBusy(true);
    setMessage(null);
    try {
      const next = await jev.saveSettings(change);
      onSaved(next);
      setForm(formOf(next));
      setMessage({ tone: "success", text: "Đã lưu cài đặt." });
    } catch (err) {
      setMessage({ tone: "danger", text: messageOf(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <ui.Card
      title="Model và hạn mức"
      aside={
        <ui.Button busy={busy} disabled={change === null || hasProblems(found)} onClick={() => void save()}>
          Lưu cài đặt
        </ui.Button>
      }
    >
      <div className="space-y-3">
        <div className="grid gap-4 md:grid-cols-2">
          <ui.Field label="Model" hint="Mặc định jev-latest" error={shown(found.model)}>
            <ui.Input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} />
          </ui.Field>
          <ui.Field
            label="Hạn mức token mỗi ngày"
            hint={capHint(parseTokens(form.cap), saved.usd_per_million_tokens)}
            error={shown(found.cap)}
          >
            <ui.Input inputMode="numeric" value={form.cap} onChange={(event) => setForm({ ...form, cap: event.target.value })} />
          </ui.Field>
        </div>
        <p className="text-label text-ink-soft">
          Chạm hạn mức thì Jev tạm nghỉ tới hết ngày (giờ Việt Nam) và tìm kiếm dùng kết quả chưa lọc.
        </p>
        {message && <ui.Notice tone={message.tone}>{message.text}</ui.Notice>}
      </div>
    </ui.Card>
  );
}

function UsageCard({ usage }: { usage: Usage | null }) {
  if (usage === null) return null;
  return (
    <ui.Card title="Đã dùng" aside={<span className="text-small text-ink-soft">{todayText(usage.used_today, usage.daily_token_cap)}</span>}>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-small">
          <thead>
            <tr className="text-label text-ink-soft">
              <th className="py-1 pr-4 font-medium">Ngày</th>
              <th className="py-1 pr-4 text-right font-medium">Lượt gọi</th>
              <th className="py-1 pr-4 text-right font-medium">Token</th>
              <th className="py-1 pr-4 text-right font-medium">Lỗi</th>
              <th className="py-1 text-right font-medium">Ước tính</th>
            </tr>
          </thead>
          <tbody>
            {usage.days.map((day) => (
              <tr key={day.date} className="border-t border-line text-ink">
                <td className="py-1.5 pr-4">{day.date}</td>
                <td className="py-1.5 pr-4 text-right">{formatCount(day.calls)}</td>
                <td className="py-1.5 pr-4 text-right">{formatCount(day.tokens)}</td>
                <td className="py-1.5 pr-4 text-right">{formatCount(day.errors)}</td>
                <td className="py-1.5 text-right">{formatUsd(day.usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ui.Card>
  );
}

export function JevPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [found, used] = await Promise.all([jev.settings(), jev.usage()]);
      setSettings(found);
      setUsage(used);
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function changed(next: Settings) {
    setSettings(next);
    void jev.usage().then(setUsage, () => undefined);
  }

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Jev"
        subtitle="Bộ chấm của TypeSafe: trả lời câu hỏi có/không bằng xác suất. Kho tri thức dùng nó để xếp lại và lọc kết quả tìm trước khi agent đọc."
      />
      {error && (
        <ui.Notice tone="danger">
          <span className="flex flex-wrap items-center justify-between gap-2">
            {error}
            <ui.Button variant="secondary" onClick={() => void load()}>
              Thử lại
            </ui.Button>
          </span>
        </ui.Notice>
      )}
      {settings === null && !error && <ui.Empty>Đang tải…</ui.Empty>}
      {settings && (
        <>
          <KeyCard saved={settings} onSaved={changed} />
          <SettingsCard saved={settings} onSaved={changed} />
          <UsageCard usage={usage} />
        </>
      )}
    </div>
  );
}
