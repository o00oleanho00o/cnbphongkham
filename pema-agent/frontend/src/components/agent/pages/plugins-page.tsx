"use client";

// Plugins của agent: the list of every plugin the agent found, one row each (name and description, origin, what it
// adds, on or off), like a connectors list. A row opens the plugin's own page, where it is switched, set up and
// where its pages are. "+ Thêm" holds the place of installing a plugin (zip, folder, git), not built yet.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button, Card, Empty, Input, Notice, PageHeader } from "@/components/agent/plugin-kit";
import { agentApi as api } from "@/lib/agent/api";
import {
  type AgentPlugin,
  contributionLine,
  originLabel,
  pluginHref,
  type PluginListing,
  PLUGINS_PATH,
  shownPlugins,
} from "@/lib/agent/plugins";
import { cx } from "@/ui/classnames";

const COLUMNS = "sm:grid-cols-[minmax(0,1fr)_7.5rem_9rem_7.5rem_1rem]";

export function PluginsPage() {
  const [listing, setListing] = useState<PluginListing | null>(null);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      setListing(await api.get<PluginListing>(PLUGINS_PATH));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = listing ? shownPlugins(listing.plugins, search) : [];
  const broken = Object.entries(listing?.broken ?? {});

  return (
    <div>
      <PageHeader
        title="Plugins"
        subtitle="Mỗi tính năng của agent là một plugin. Bấm vào một plugin để bật, tắt, cài đặt và mở trang của nó."
        aside={
          <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
            <label className="min-w-0 flex-1 sm:w-64 sm:flex-none">
              <span className="sr-only">Tìm plugin</span>
              <Input
                type="search"
                placeholder="Tìm plugin"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <Button aria-expanded={adding} onClick={() => setAdding(!adding)}>
              + Thêm
            </Button>
          </div>
        }
      />
      {adding && (
        <div className="mb-4">
          <Notice>
            Sắp có: cài thêm plugin từ file zip, thư mục hoặc git. Hiện agent dùng các plugin có sẵn
            bên dưới.
          </Notice>
        </div>
      )}
      {error && <Notice tone="danger">{error}</Notice>}
      {listing && (
        <Card>
          <div
            aria-hidden
            className={cx(
              "hidden gap-3 border-b border-line px-3 pb-2 text-label text-ink-soft sm:grid",
              COLUMNS,
            )}
          >
            <span>Plugin</span>
            <span>Loại</span>
            <span>Đóng góp</span>
            <span>Trạng thái</span>
            <span />
          </div>
          {shown.length === 0 ? (
            <Empty>{search ? "Không có plugin nào khớp." : "Không tìm thấy plugin nào."}</Empty>
          ) : (
            <ul aria-label="Danh sách plugin" className="divide-y divide-line">
              {shown.map((plugin) => (
                <li key={plugin.name}>
                  <PluginRow plugin={plugin} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {broken.length > 0 && (
        <div className="mt-6">
          <Card title="Plugin không đọc được">
            <ul className="space-y-1 text-small text-danger">
              {broken.map(([name, why]) => (
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

function PluginRow({ plugin }: { plugin: AgentPlugin }) {
  const adds = contributionLine(plugin);
  return (
    <Link
      href={pluginHref(plugin.name)}
      className={cx(
        "grid min-h-14 grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-control px-3 py-3 hover:bg-row-hover",
        COLUMNS,
      )}
    >
      <span className="min-w-0">
        <span className="block font-semibold text-ink">{plugin.name}</span>
        {plugin.description && (
          <span className="block truncate text-small text-ink-soft">{plugin.description}</span>
        )}
      </span>
      <span className="hidden text-small text-ink-soft sm:block">{originLabel(plugin.origin)}</span>
      <span className="hidden text-small text-ink-soft sm:block">{adds || "—"}</span>
      <PluginStatus plugin={plugin} />
      <span aria-hidden className="hidden text-ink-soft sm:block">
        ›
      </span>
    </Link>
  );
}

export function PluginStatus({ plugin }: { plugin: AgentPlugin }) {
  if (plugin.error) return <span className="text-small font-medium text-danger">Có lỗi</span>;
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 text-small",
        plugin.enabled ? "font-medium text-success" : "text-ink-soft",
      )}
    >
      <span
        aria-hidden
        className={cx(
          "size-2 rounded-full",
          plugin.enabled ? "bg-success" : "border border-line-strong",
        )}
      />
      {plugin.enabled ? "Đang bật" : "Đang tắt"}
    </span>
  );
}
