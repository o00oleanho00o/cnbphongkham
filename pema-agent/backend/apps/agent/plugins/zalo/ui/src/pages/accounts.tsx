/** The plugin's Zalo accounts: add, switch on or off, log in by QR, change, delete. */
import { useState } from "react";

import { messageOf, zalo } from "../client";
import { CHANNEL_LABEL } from "../logic";
import { useAccounts } from "../parts";
import { ui } from "../sdk";
import type { Account } from "../types";
import { AccountDrawer } from "./account-drawer";
import { QrLogin } from "./qr-login";

const CREDENTIAL: Record<Account["channel"], [string, string]> = {
  zalo_personal: ["Đã đăng nhập", "Chưa đăng nhập"],
  zalo_bot: ["Có token", "Chưa có token"],
  zalo_oa: ["Có khóa OA", "Chưa có khóa OA"],
};

export function AccountsPage() {
  const { accounts, error, reload } = useAccounts();
  const [editing, setEditing] = useState<Account | "new" | null>(null);
  const [qrFor, setQrFor] = useState<Account | null>(null);

  function saved(account: Account, created: boolean) {
    setEditing(null);
    void reload();
    if (created && account.channel === "zalo_personal") setQrFor(account);
  }

  return (
    <div>
      <ui.PageHeader
        title="Tài khoản Zalo"
        subtitle="Nick cá nhân (quét QR), bot chính thức (token) và Zalo OA mà agent nói chuyện qua"
        aside={
          <div className="flex gap-2">
            <ui.Button variant="secondary" onClick={() => void reload()}>
              Làm mới
            </ui.Button>
            <ui.Button onClick={() => setEditing("new")}>Thêm tài khoản</ui.Button>
          </div>
        }
      />
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {accounts?.length === 0 && <ui.Empty>Chưa có tài khoản nào. Bấm "Thêm tài khoản" để bắt đầu.</ui.Empty>}
      <div className="space-y-4">
        {accounts?.map((account) => (
          <AccountCard
            key={account.id}
            account={account}
            onEdit={() => setEditing(account)}
            onQr={() => setQrFor(account)}
            onChanged={() => void reload()}
          />
        ))}
      </div>
      {editing && (
        <AccountDrawer account={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={saved} />
      )}
      {qrFor && (
        <QrLogin
          account={qrFor}
          onClose={() => {
            setQrFor(null);
            void reload();
          }}
        />
      )}
    </div>
  );
}

function AccountCard({
  account,
  onEdit,
  onQr,
  onChanged,
}: {
  account: Account;
  onEdit: () => void;
  onQr: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function remove() {
    if (!window.confirm(`Xóa tài khoản "${account.label}"? Phiên đăng nhập và token đã lưu cũng bị xóa.`)) return;
    void run(() => zalo.remove(account.id));
  }

  const [has, lacks] = CREDENTIAL[account.channel];
  return (
    <ui.Card
      title={
        <span className="flex flex-wrap items-center gap-2">
          {account.label}
          <ui.Badge tone="info">{CHANNEL_LABEL[account.channel]}</ui.Badge>
          {account.running ? <ui.Badge tone="success">Đang chạy</ui.Badge> : <ui.Badge>Đang dừng</ui.Badge>}
          <ui.Badge tone={account.has_credentials ? "success" : "warning"}>{account.has_credentials ? has : lacks}</ui.Badge>
        </span>
      }
      aside={
        <ui.Toggle
          checked={account.enabled}
          disabled={busy}
          label={`Bật tài khoản ${account.label}`}
          onChange={(on) => void run(() => zalo.update(account.id, { enabled: on }))}
        />
      }
    >
      <p className="font-mono text-label text-ink-soft">{account.id}</p>
      <p className="mt-1 text-small text-ink-soft">
        {account.allowlist.mode === "all"
          ? "Trả lời tất cả mọi người"
          : `Chỉ trả lời ${account.allowlist.user_ids.length} người trong danh sách`}
      </p>
      {account.warning && (
        <div className="mt-3">
          <ui.Notice tone="warning">{account.warning}</ui.Notice>
        </div>
      )}
      {error && (
        <div className="mt-3">
          <ui.Notice tone="danger">{error}</ui.Notice>
        </div>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        {account.channel === "zalo_personal" && (
          <ui.Button disabled={busy} onClick={onQr}>
            {account.has_credentials ? "Quét lại mã QR" : "Quét mã QR"}
          </ui.Button>
        )}
        <ui.Button variant="secondary" disabled={busy} onClick={onEdit}>
          Sửa
        </ui.Button>
        <ui.Button variant="danger" disabled={busy} onClick={remove}>
          Xóa
        </ui.Button>
      </div>
    </ui.Card>
  );
}
