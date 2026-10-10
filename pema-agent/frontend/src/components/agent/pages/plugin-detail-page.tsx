"use client";

// The page of one agent plugin (`/admin/agent/plugins/<name>`), opened from the Plugins list: its name and switch,
// then tabs: "Tổng quan" (errors, what it adds, its settings) and the pages the plugin ships itself (Zalo: accounts,
// contacts...), drawn at `/admin/agent/plugins/<name>/<page>`.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  failure,
  pluginPageHref,
  PluginsProblem,
  type PluginsState,
  useAgentPlugins,
} from "@/components/agent/agent-plugins";
import { PluginPageHost } from "@/components/agent/plugin-page-host";
import { Badge, Card, Notice, Toggle } from "@/components/agent/plugin-kit";
import { PluginSettingsForm } from "@/components/agent/plugin-settings-form";
import { PluginStatus } from "@/components/agent/pages/plugins-page";
import { SubNav } from "@/components/agent/sub-nav";
import { agentApi as api } from "@/lib/agent/api";
import {
  type AgentPlugin,
  originLabel,
  pluginHref,
  type PluginListing,
  PLUGINS_HREF,
  PLUGINS_PATH,
} from "@/lib/agent/plugins";
import { loadPlugins } from "@/lib/agent/sdk";
import { buttonClass } from "@/ui/button";
import { EmptyState } from "@/ui/empty-state";
import { PageHeading } from "@/ui/workspace";

type Loaded =
  Exclude<PluginsState, { kind: "ready" }> | { kind: "ready"; plugin: AgentPlugin | null };

export function PluginDetailPage({ name, pageId }: { name: string; pageId?: string }) {
  const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let stale = false;
    api.get<PluginListing>(PLUGINS_PATH).then(
      (listing) => {
        if (stale) return;
        setLoaded({ kind: "ready", plugin: listing.plugins.find((p) => p.name === name) ?? null });
      },
      (err: unknown) => {
        if (!stale) setLoaded(failure(err));
      },
    );
    return () => {
      stale = true;
    };
  }, [name, attempt]);

  const retry = useCallback(() => {
    setLoaded({ kind: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const changed = useCallback((next: AgentPlugin) => {
    setLoaded({ kind: "ready", plugin: next });
    void loadPlugins().catch(() => undefined);
  }, []);

  if (loaded.kind !== "ready") return <PluginsProblem state={loaded} retry={retry} />;
  if (!loaded.plugin) {
    return (
      <EmptyState
        title="Không có plugin này"
        hint={`Agent không tìm thấy plugin ${name}.`}
        action={
          <Link href={PLUGINS_HREF} className={buttonClass("secondary")}>
            Về danh sách plugin
          </Link>
        }
      />
    );
  }
  const plugin = loaded.plugin;
  return (
    <div>
      <Link
        href={PLUGINS_HREF}
        className="mb-2 inline-flex min-h-11 items-center text-small text-link hover:underline lg:min-h-9"
      >
        ‹ Plugins
      </Link>
      <PluginHeader plugin={plugin} onChanged={changed} />
      <PluginTabs plugin={plugin} />
      {pageId ? (
        <PluginPageHost plugin={plugin.name} pageId={pageId} />
      ) : (
        <PluginOverview plugin={plugin} onChanged={changed} />
      )}
    </div>
  );
}

function PluginHeader({
  plugin,
  onChanged,
}: {
  plugin: AgentPlugin;
  onChanged: (next: AgentPlugin) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function toggle(on: boolean) {
    setBusy(true);
    setError("");
    try {
      onChanged(
        await api.post<AgentPlugin>(`${PLUGINS_PATH}/${plugin.name}/${on ? "enable" : "disable"}`),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeading
        title={plugin.name}
        subtitle={plugin.description || undefined}
        actions={
          <span className="flex items-center gap-2">
            <PluginStatus plugin={plugin} />
            <Toggle
              checked={plugin.enabled}
              disabled={busy}
              label={`Bật plugin ${plugin.name}`}
              onChange={(on) => void toggle(on)}
            />
          </span>
        }
      />
      <p className="-mt-2 mb-4 flex flex-wrap gap-2">
        <Badge>{plugin.version}</Badge>
        <Badge tone="info">{originLabel(plugin.origin)}</Badge>
      </p>
      {error && (
        <div className="mb-4">
          <Notice tone="danger">{error}</Notice>
        </div>
      )}
    </>
  );
}

function PluginTabs({ plugin }: { plugin: AgentPlugin }) {
  const { registered } = useAgentPlugins();
  const pages = plugin.enabled ? (registered.get(plugin.name)?.pages ?? []) : [];
  const items = [
    { href: pluginHref(plugin.name), label: "Tổng quan", exact: true },
    ...pages.map((page) => ({
      href: pluginPageHref(plugin.name, page.id),
      label: page.title,
    })),
  ];
  return <SubNav label={`Trang của plugin ${plugin.name}`} items={items} />;
}

function NameList({ title, names }: { title: string; names: readonly string[] }) {
  if (names.length === 0) return null;
  return (
    <div>
      <dt className="text-label text-ink-soft">{title}</dt>
      <dd className="mt-0.5 text-body break-words text-ink">{names.join(", ")}</dd>
    </div>
  );
}

function PluginOverview({
  plugin,
  onChanged,
}: {
  plugin: AgentPlugin;
  onChanged: (next: AgentPlugin) => void;
}) {
  const adds = plugin.tools.length + plugin.channels.length + plugin.jobs.length;
  return (
    <div className="space-y-4">
      {plugin.error && <Notice tone="danger">{plugin.error}</Notice>}
      {plugin.secrets_unreadable && (
        <Notice tone="warning">
          Cài đặt bí mật đã lưu không đọc được (khóa bí mật của agent đã đổi).
        </Notice>
      )}
      <Card title="Đóng góp cho agent">
        {adds === 0 ? (
          <p className="text-small text-ink-soft">
            {plugin.enabled
              ? "Plugin này không thêm tool, kênh hay việc nền nào."
              : "Bật plugin để xem nó thêm gì cho agent."}
          </p>
        ) : (
          <dl className="space-y-2">
            <NameList title="Tool" names={plugin.tools} />
            <NameList title="Kênh" names={plugin.channels} />
            <NameList title="Việc nền" names={plugin.jobs} />
          </dl>
        )}
      </Card>
      <Card title="Cài đặt">
        {plugin.settings.length === 0 ? (
          <p className="text-small text-ink-soft">Plugin này không có cài đặt.</p>
        ) : (
          <PluginSettingsForm key={plugin.version} plugin={plugin} onChanged={onChanged} />
        )}
      </Card>
    </div>
  );
}
