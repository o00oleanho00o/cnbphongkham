"use client";

// The settings of one plugin: a form drawn from its manifest (`PATCH /v1/admin/plugins/<name>/settings`). Only the
// fields that changed are sent; a secret left empty keeps the stored one.
import { type FormEvent, useState } from "react";

import { Button, Field, Input, Notice, Toggle } from "@/components/agent/plugin-kit";
import { agentApi as api } from "@/lib/agent/api";
import { type AgentPlugin, PLUGINS_PATH, type PluginSetting } from "@/lib/agent/plugins";

type Draft = Record<string, string | boolean>;

function draftOf(settings: PluginSetting[]): Draft {
  return Object.fromEntries(
    settings.map((s) => [
      s.key,
      s.type === "boolean"
        ? s.value === true
        : s.sensitive || s.value == null
          ? ""
          : String(s.value),
    ]),
  );
}

export function PluginSettingsForm({
  plugin,
  onChanged,
}: {
  plugin: AgentPlugin;
  onChanged: (next: AgentPlugin) => void;
}) {
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
      const next = await api.patch<AgentPlugin>(`${PLUGINS_PATH}/${plugin.name}/settings`, {
        settings: changes,
      });
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
    <form onSubmit={save} className="space-y-3">
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
              placeholder={
                setting.sensitive && setting.value
                  ? `${String(setting.value)} (để trống: giữ nguyên)`
                  : ""
              }
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

function valueOf(setting: PluginSetting, value: string | boolean): unknown {
  if (typeof value === "boolean") return value;
  if (value === "") return null;
  if (setting.type === "integer") return Number.parseInt(value, 10);
  if (setting.type === "number") return Number(value);
  return value;
}

function sourceText(setting: PluginSetting): string {
  if (setting.source === "admin") return "đã lưu";
  if (setting.source === "profile") return "theo profile";
  if (setting.source === "default") return "mặc định";
  return "";
}
