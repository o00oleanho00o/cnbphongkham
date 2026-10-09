/** QR login of a personal account: start the session, then ask its state every 1.5 s until it ends. */
import { useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { QR_TEXT, type QrView, qrView } from "../logic";
import { Dialog } from "../parts";
import { ui } from "../sdk";
import type { Account } from "../types";

const POLL_MS = 1500;

export function QrLogin({ account, onClose }: { account: Account; onClose: () => void }) {
  const [view, setView] = useState<QrView>({ state: "starting", image: null, error: null, done: false });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setView({ state: "starting", image: null, error: null, done: false });

    async function step(first: boolean) {
      let next: QrView;
      try {
        next = qrView(first ? await zalo.startLogin(account.id) : await zalo.loginStatus(account.id));
      } catch (err) {
        next = { state: "error", image: null, error: messageOf(err), done: true };
      }
      if (stopped) return;
      setView(next);
      if (!next.done) timer = setTimeout(() => void step(false), POLL_MS);
    }

    void step(true);
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [account.id, attempt]);

  const failed = view.state === "expired" || view.state === "error";
  return (
    <Dialog title={`Đăng nhập QR - ${account.label}`} onClose={onClose}>
      <p className="mb-4 text-small text-ink-soft" aria-live="polite">
        {QR_TEXT[view.state]}
      </p>
      <div className="mx-auto mb-4 flex h-56 w-56 items-center justify-center rounded-tile border border-line bg-surface">
        <QrBody view={view} />
      </div>
      {view.error && <p className="mb-3 text-small break-words text-danger">{view.error}</p>}
      <div className="flex justify-center gap-3">
        {failed && <ui.Button onClick={() => setAttempt((n) => n + 1)}>Thử lại</ui.Button>}
        <ui.Button variant="secondary" onClick={onClose}>
          {view.state === "success" ? "Xong" : "Đóng"}
        </ui.Button>
      </div>
    </Dialog>
  );
}

function QrBody({ view }: { view: QrView }) {
  if (view.image) return <img src={view.image} alt="Mã QR đăng nhập Zalo" className="h-52 w-52" />;
  if (view.state === "success") return <span className="text-5xl">✅</span>;
  if (view.state === "scanned") return <span className="text-5xl">📱</span>;
  if (view.state === "expired" || view.state === "error") return <span className="text-5xl">⚠️</span>;
  return <span className="animate-pulse text-small text-ink-soft">Đang tải mã QR...</span>;
}
