/** The Node bridge personal accounts log in through: install it here (it takes minutes), see it run, remove it. */
import { useCallback, useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { ui } from "../sdk";
import type { Bridge } from "../types";

const INSTALL_POLL_MS = 2000;

export function BridgePage() {
  const [bridge, setBridge] = useState<Bridge | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setBridge(await zalo.bridge());
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const installing = bridge?.installing ?? false;
  useEffect(() => {
    if (!installing) return;
    const timer = setInterval(() => void reload(), INSTALL_POLL_MS);
    return () => clearInterval(timer);
  }, [installing, reload]);

  async function run(action: () => Promise<Bridge>) {
    setBusy(true);
    setError("");
    try {
      setBridge(await action());
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function uninstall() {
    if (!window.confirm("Gỡ cầu nối? Các nick cá nhân ngừng chạy cho tới khi cài lại.")) return;
    void run(zalo.uninstallBridge);
  }

  const external = bridge?.version === "external";
  return (
    <div>
      <ui.PageHeader
        title="Cầu nối Zalo cá nhân"
        subtitle="Chương trình Node (zca-js) mà nick cá nhân đăng nhập và nhắn tin qua. Bot chính thức và OA không cần."
        aside={
          <ui.Button variant="secondary" onClick={() => void reload()}>
            Làm mới
          </ui.Button>
        }
      />
      <div className="mb-4">
        <ui.Notice tone="warning">
          Nick cá nhân dùng giao thức không chính thức của Zalo: nick có thể bị khóa. Chỉ dùng nick phụ.
        </ui.Notice>
      </div>
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
              {installing ? (
                <ui.Badge tone="info">Đang cài</ui.Badge>
              ) : bridge.installed ? (
                <ui.Badge tone="success">Đã cài{bridge.version && !external ? ` ${bridge.version}` : ""}</ui.Badge>
              ) : (
                <ui.Badge tone="warning">Chưa cài</ui.Badge>
              )}
              {bridge.running ? <ui.Badge tone="success">Đang chạy</ui.Badge> : <ui.Badge>Không chạy</ui.Badge>}
            </span>
          }
        >
          {external && <p className="text-small text-ink-soft">Cầu nối chạy ngoài plugin, không cài hay gỡ ở đây.</p>}
          {!bridge.installed && !installing && (
            <p className="text-small text-ink-soft">Cần Node 22 và pnpm trên máy chạy agent. Cài mất vài phút.</p>
          )}
          {bridge.error && (
            <div className="mt-3">
              <ui.Notice tone="danger">{bridge.error}</ui.Notice>
            </div>
          )}
          {!external && (
            <div className="mt-4 flex flex-wrap gap-2">
              <ui.Button busy={busy || installing} onClick={() => void run(zalo.installBridge)}>
                {bridge.installed ? "Cài lại" : "Cài cầu nối"}
              </ui.Button>
              {bridge.installed && (
                <ui.Button variant="danger" disabled={busy || installing} onClick={uninstall}>
                  Gỡ
                </ui.Button>
              )}
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
