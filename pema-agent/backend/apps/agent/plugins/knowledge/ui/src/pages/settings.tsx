/** Cài đặt: embedding, judging with Jev, search, benchmark; each section saves on its own. */
import { useCallback, useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import { ui } from "../sdk";
import { BenchmarkSection } from "../settings/benchmark-section";
import { EmbeddingSection } from "../settings/embedding-section";
import { JudgingSection } from "../settings/judging-section";
import { SearchSection } from "../settings/search-section";
import type { KnowledgeSettings } from "../types";

export function SettingsPage() {
  const [settings, setSettings] = useState<KnowledgeSettings | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setSettings(await knowledge.settings());
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Cài đặt"
        subtitle="Mỗi phần có nút Lưu riêng. Thay đổi áp dụng từ lần tìm hoặc lần nạp kế tiếp."
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
          <EmbeddingSection settings={settings} onSaved={setSettings} />
          <JudgingSection settings={settings} onSaved={setSettings} />
          <SearchSection settings={settings} onSaved={setSettings} />
          <BenchmarkSection settings={settings} onSaved={setSettings} />
        </>
      )}
    </div>
  );
}
