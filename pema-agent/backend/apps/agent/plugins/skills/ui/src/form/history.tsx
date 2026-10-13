/** The versions of an item, newest first; an older one can be put back (it becomes a new version). */
import { useCallback, useEffect, useState } from "react";

import { messageOf, skills } from "../client";
import { formatTime, scopesSummary } from "../logic";
import { ui } from "../sdk";
import type { Saved, Version } from "../types";

export function History({ itemId, onRestored }: { itemId: string; onRestored: (saved: Saved) => void }) {
  const [versions, setVersions] = useState<Version[] | null>(null);
  const [error, setError] = useState("");
  const [asking, setAsking] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      setVersions((await skills.versions(itemId)).versions);
    } catch (err) {
      setError(messageOf(err));
      setVersions([]);
    }
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function restore(version: number) {
    setBusy(true);
    setError("");
    try {
      onRestored(await skills.restore(itemId, version));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
      setAsking(null);
    }
  }

  return (
    <div className="space-y-3">
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {versions === null && <ui.Empty>Đang tải…</ui.Empty>}
      {versions !== null && versions.length === 0 && !error && <ui.Empty>Chưa có phiên bản nào.</ui.Empty>}
      <ul className="space-y-2">
        {(versions ?? []).map((version, index) => (
          <li key={version.version} className="space-y-2 rounded-tile border border-line p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-body text-ink">
                <span className="font-bold text-heading">Phiên bản {version.version}</span>
                {index === 0 && <span className="ml-2 text-small text-ink-soft">(đang dùng)</span>}
                <span className="ml-2 text-small text-ink-soft">
                  {version.changed_by} · {formatTime(version.created_at)}
                </span>
              </p>
              {index > 0 && asking !== version.version && (
                <ui.Button variant="secondary" onClick={() => setAsking(version.version)}>
                  Khôi phục
                </ui.Button>
              )}
              {asking === version.version && (
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-small text-ink-soft">Đặt lại thành phiên bản mới?</span>
                  <ui.Button busy={busy} onClick={() => void restore(version.version)}>
                    Khôi phục
                  </ui.Button>
                  <ui.Button variant="ghost" onClick={() => setAsking(null)}>
                    Hủy
                  </ui.Button>
                </span>
              )}
            </div>
            {version.reason && <p className="text-small text-ink-soft">Lý do: {version.reason}</p>}
            <p className="text-small text-ink-soft">Áp dụng: {scopesSummary(version.snapshot.scopes)}</p>
            <details>
              <summary className="cursor-pointer text-small text-link">Xem nội dung</summary>
              <p className="mt-2 text-small font-medium text-ink">{version.snapshot.description}</p>
              <pre className="mt-1 max-h-72 overflow-auto rounded-tile border border-line bg-tile p-3 text-small whitespace-pre-wrap text-ink">
                {version.snapshot.body}
              </pre>
            </details>
          </li>
        ))}
      </ul>
    </div>
  );
}
