/** The Bun bridge personal accounts log in through: it is part of the connector (baked into its image, started by the
 * connector when a personal account is on), so this page only shows how it is doing. */
import { useCallback, useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { ui } from "../sdk";
import type { Bridge } from "../types";

export function BridgePage() {
  const [bridge, setBridge] = useState<Bridge | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    try {
      setBridge(await zalo.bridge());
      setError("");
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div>
      <ui.PageHeader
        title="Cầu nối Zalo cá nhân"
        subtitle="Chương trình Bun (zca-js) mà nick cá nhân đăng nhập và nhắn tin qua, một phần của connector Zalo. Bot chính thức và OA không cần."
        aside={
          <ui.Button variant="secondary" onClick={() => void reload()}>
            Làm mới
          </ui.Button>
        }
      />
      {error && (
        <div className="mb-4">
          <ui.Notice tone="danger">{error}</ui.Notice>
        </div>
      )}
      {bridge && (
        <ui.Card
          title={
            <span className="flex flex-wrap items-center gap-2">
              Trạng thái
              {bridge.running ? <ui.Badge tone="success">Đang chạy</ui.Badge> : <ui.Badge>Không chạy</ui.Badge>}
              {bridge.version && <ui.Badge>{bridge.version}</ui.Badge>}
            </span>
          }
        >
          <p className="text-small text-ink-soft">
            Có sẵn trong connector: tự chạy khi có nick cá nhân đang bật, không cần cài.
          </p>
          {bridge.error && (
            <div className="mt-3">
              <ui.Notice tone="danger">{bridge.error}</ui.Notice>
            </div>
          )}
          {bridge.log.length > 0 && (
            <pre className="mt-4 max-h-64 overflow-auto rounded-tile border border-line bg-tile p-3 text-label whitespace-pre-wrap text-ink-soft">
              {bridge.log.join("\n")}
            </pre>
          )}
        </ui.Card>
      )}
    </div>
  );
}
