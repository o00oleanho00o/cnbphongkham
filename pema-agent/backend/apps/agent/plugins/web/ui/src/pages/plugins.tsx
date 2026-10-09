/** Every plugin found: switch it on or off and change its settings (a form drawn from its manifest). */
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import { loadPlugins } from "../sdk";
import { Badge, Button, Card, Empty, Field, Input, Notice, PageHeader, Toggle } from "../ui/kit";

interface Setting {
  key: string;
  type: "string" | "number" | "integer" | "boolean";
  title: string;
  description: string;
  required: boolean;
  sensitive: boolean;
  default: unknown;
  value: unknown;
  source: "admin" | "profile" | "default" | null;
}

interface Plugin {
  name: string;
  version: string;
  description: string;
  origin: string;
  enabled: boolean;
  error: string | null;
  tools: string[];
  channels: string[];
  jobs: string[];
  settings: Setting[];
  secrets_unreadable: boolean;
}

interface Listing {
  plugins: Plugin[];
  broken: Record<string, string>;
}

/** Switching it off would close the dashboard that switches it back on. */
const KEEP_ON = "web";

export function PluginsPage() {
  const [listing, setListing] = useState<Listing | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setListing(await api.get<Listing>("/v1/admin/plugins"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const changed = useCallback(
    (next: Plugin) => {
      setListing((before) =>
        before && { ...before, plugins: before.plugins.map((p) => (p.name === next.name ? next : p)) },
      );
      void loadPlugins().catch(() => undefined);
    },
    [],
  );

  return (
    <div>
      <PageHeader title="Plugins" subtitle="Mọi tính năng của agent là một plugin: bật, tắt và cài đặt ở đây" />
      {error && <Notice tone="danger">{error}</Notice>}
      {listing && listing.plugins.length === 0 && <Empty>Không tìm thấy plugin nào.</Empty>}
      <div className="space-y-4">
        {listing?.plugins.map((plugin) => <PluginCard key={plugin.name} plugin={plugin} onChanged={changed} />)}
      </div>
      {listing && Object.keys(listing.broken).length > 0 && (
        <div className="mt-6">
          <Card title="Plugin không đọc được">
            <ul className="space-y-1 text-small text-danger">
              {Object.entries(listing.broken).map(([name, why]) => (
                <li key={name} className="break-words">
                  <b>{name}</b>: {why}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  );
}

function PluginCard({ plugin, onChanged }: { plugin: Plugin; onChanged: (next: Plugin) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);

  async function toggle(on: boolean) {
    setBusy(true);
    setError("");
    try {
      onChanged(await api.post<Plugin>(`/v1/admin/plugins/${plugin.name}/${on ? "enable" : "disable"}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  const parts = [
    plugin.tools.length && `${plugin.tools.length} tool`,
    plugin.channels.length && `${plugin.channels.length} kênh`,
    plugin.jobs.length && `${plugin.jobs.length} việc nền`,
  ].filter(Boolean);

  return (
    <Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          {plugin.name}
          <Badge>{plugin.version}</Badge>
          <Badge tone="info">{plugin.origin}</Badge>
          {plugin.enabled ? <Badge tone="success">Đang bật</Badge> : <Badge>Đang tắt</Badge>}
        </span>
      }
      aside={
        <Toggle
          checked={plugin.enabled}
          disabled={busy || plugin.name === KEEP_ON}
          label={`Bật plugin ${plugin.name}`}
          onChange={(on) => void toggle(on)}
        />
      }
    >
      {plugin.description && <p className="text-small text-ink-soft">{plugin.description}</p>}
      {parts.length > 0 && <p className="mt-2 text-label text-ink-soft">Đóng góp: {parts.join(" · ")}</p>}
      {plugin.name === KEEP_ON && (
        <p className="mt-2 text-label text-ink-soft">Không tắt được ở đây: tắt plugin này là mất bảng điều khiển.</p>
      )}
      {(error || plugin.error) && (
        <div className="mt-3">
          <Notice tone="danger">{error || plugin.error}</Notice>
        </div>
      )}
      {plugin.secrets_unreadable && (
        <div className="mt-3">
          <Notice tone="warning">Cài đặt bí mật đã lưu không đọc được (khóa bí mật của agent đã đổi).</Notice>
        </div>
      )}
      {plugin.settings.length > 0 && (
        <div className="mt-3">
          <Button variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Ẩn cài đặt" : `Cài đặt (${plugin.settings.length})`}
          </Button>
          {open && <SettingsForm plugin={plugin} onChanged={onChanged} />}
        </div>
      )}
    </Card>
  );
}

type Draft = Record<string, string | boolean>;

function draftOf(settings: Setting[]): Draft {
  return Object.fromEntries(
    settings.map((s) => [
      s.key,
      s.type === "boolean" ? s.value === true : s.sensitive || s.value == null ? "" : String(s.value),
    ]),
  );
}

function SettingsForm({ plugin, onChanged }: { plugin: Plugin; onChanged: (next: Plugin) => void }) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(plugin.settings));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    const changes: Record<string, unknown> = {};
    const initial = draftOf(plugin.settings);
    for (const setting of plugin.settings) {
      const value = draft[setting.key];
      if (value === undefined || value === initial[setting.key]) continue;
      if (setting.sensitive && value === "") continue;
      changes[setting.key] = valueOf(setting, value);
    }
    setBusy(true);
    setNotice(null);
    try {
      const next = await api.patch<Plugin>(`/v1/admin/plugins/${plugin.name}/settings`, { settings: changes });
      onChanged(next);
      setDraft(draftOf(next.settings));
      setNotice({ tone: "success", text: "Đã lưu, plugin đã nạp lại." });
    } catch (err) {
      setNotice({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="mt-3 space-y-3 rounded-tile border border-line p-4">
      {plugin.settings.map((setting) => {
        const label = setting.title || setting.key;
        const hint = [setting.description, sourceText(setting)].filter(Boolean).join(" - ");
        if (setting.type === "boolean") {
          return (
            <div key={setting.key} className="flex items-center justify-between gap-3">
              <span>
                <span className="block text-small font-medium">{label}</span>
                {hint && <span className="block text-label text-ink-soft">{hint}</span>}
              </span>
              <Toggle
                checked={draft[setting.key] === true}
                label={label}
                onChange={(on) => setDraft({ ...draft, [setting.key]: on })}
              />
            </div>
          );
        }
        return (
          <Field key={setting.key} label={label} hint={hint}>
            <Input
              type={setting.sensitive ? "password" : setting.type === "string" ? "text" : "number"}
              step={setting.type === "integer" ? 1 : "any"}
              required={setting.required && !setting.sensitive}
              placeholder={setting.sensitive && setting.value ? `${String(setting.value)} (để trống: giữ nguyên)` : ""}
              value={String(draft[setting.key] ?? "")}
              onChange={(e) => setDraft({ ...draft, [setting.key]: e.target.value })}
            />
          </Field>
        );
      })}
      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
      <Button type="submit" busy={busy}>
        Lưu cài đặt
      </Button>
    </form>
  );
}

function valueOf(setting: Setting, value: string | boolean): unknown {
  if (typeof value === "boolean") return value;
  if (value === "") return null;
  if (setting.type === "integer") return Number.parseInt(value, 10);
  if (setting.type === "number") return Number(value);
  return value;
}

function sourceText(setting: Setting): string {
  if (setting.source === "admin") return "đã lưu";
  if (setting.source === "profile") return "theo profile";
  if (setting.source === "default") return "mặc định";
  return "";
}
