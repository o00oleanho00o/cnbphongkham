// ported from: web/src/pages/accounts-page.tsx
//
// Deviations: route page (`export default`) instead of a named component; DTOs and calls are the
// contract's (`AccountOut`, `AgentOut`, `GET/PATCH/DELETE /admin/accounts`); the original `loai` is
// `channel` (`zalo_bot` | `zalo_personal` | `zalo_oa`) and `coBotToken` is `has_bot_token`. The
// `warning` that `update()` used to return does not exist in the contract, so it is gone. After a
// change the page also refreshes the shell's account list (`useAdminAccounts().reload`). NEW: the
// channel switchboard (kill switch, daily cap, window) on top, and the policy profile badge per account.
"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import { AccountEditDrawer } from "@/components/admin/accounts/account-edit-drawer";
import { PolicyProfileBadge } from "@/components/admin/accounts/policy-profile-badge";
import { QrLoginModal } from "@/components/admin/accounts/qr-login-modal";
import { ChannelSettingsPanel } from "@/components/admin/channels/channel-settings-panel";
import { NHAN_KENH_NGAN } from "@/lib/admin/accounts/mo-ta-loai-kenh";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Account, Agent } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type BadgeTone = "blue" | "gray" | "green" | "red" | "amber";

const NOTICE_CLASS: Record<"red" | "amber", string> = {
  red: "text-danger",
  amber: "text-warning",
};

/**
 * Nhãn trạng thái của một account. Tài khoản bot không login QR mà nhập token, nên nhãn "chưa
 * login QR" là chỉ sai đường ngay ở chỗ người ta nhìn đầu tiên.
 */
function statusBadge(acc: Account): { tone: BadgeTone; text: string } {
  if (acc.running) return { tone: "green", text: "Đang chạy" };
  if (acc.channel === "zalo_bot") {
    return acc.has_bot_token
      ? { tone: "gray", text: "Đã có token, chưa chạy" }
      : { tone: "amber", text: "Chưa nhập token" };
  }
  if (acc.channel === "zalo_oa") return { tone: "gray", text: "Chưa hỗ trợ" };
  return acc.has_credentials
    ? { tone: "gray", text: "Đã login, chưa chạy" }
    : { tone: "amber", text: "Chưa login QR" };
}

/** Trang Accounts: tài khoản Zalo (kênh) - thêm, đổi tên, bật/tắt, gắn não, login QR */
export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [editing, setEditing] = useState<Account | null>(null);
  const [creating, setCreating] = useState(false);
  const [qrAccount, setQrAccount] = useState<Account | null>(null);
  const [notice, setNotice] = useState<{ tone: "red" | "amber"; text: string } | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();
  const { reload: reloadShell } = useAdminAccounts();

  const reload = useCallback(async () => {
    // Danh sách agent chỉ để hiện tên não; thiếu quyền admin.agents thì vẫn xem được account.
    const [accs, ags] = await Promise.all([
      unwrap(http.GET("/api/v1/admin/accounts")),
      unwrap(http.GET("/api/v1/admin/agents")).catch((): Agent[] => []),
    ]);
    setAccounts(accs);
    setAgents(ags);
    reloadShell();
  }, [reloadShell]);

  useEffect(() => {
    reload().catch(() => setNotice({ tone: "red", text: "Không tải được danh sách" }));
  }, [reload]);

  async function toggleEnabled(acc: Account) {
    setNotice(null);
    try {
      await unwrap(
        http.PATCH("/api/v1/admin/accounts/{account_id}", {
          params: { path: { account_id: acc.id } },
          body: { enabled: !acc.enabled },
        }),
      );
      await reload();
    } catch (err) {
      setNotice({ tone: "red", text: errorMessage(err) });
    }
  }

  async function remove(acc: Account) {
    const ok = await confirm({
      title: `Xóa account "${acc.label}"?`,
      message: "Credentials đăng nhập Zalo sẽ bị xóa, lịch sử hội thoại vẫn giữ lại.",
    });
    if (!ok) return;
    setNotice(null);
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/accounts/{account_id}", {
          params: { path: { account_id: acc.id } },
        }),
      );
      await reload();
    } catch (err) {
      setNotice({ tone: "red", text: errorMessage(err) });
    }
  }

  const agentName = (id: string) => agents.find((a) => a.id === id);

  const closeDrawer = useCallback(() => {
    setEditing(null);
    setCreating(false);
  }, []);

  const onSaved = useCallback(() => {
    setEditing(null);
    setCreating(false);
    void reload();
  }, [reload]);

  const closeQr = useCallback(() => {
    setQrAccount(null);
    void reload();
  }, [reload]);

  return (
    <div>
      <PageHeader
        title="Tài khoản Zalo"
        subtitle="Tài khoản Zalo của bot - mỗi account gắn một agent (não) và có policies riêng"
        aside={
          <button
            onClick={() => setCreating(true)}
            className="min-h-11 rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white hover:bg-brand-600 sm:min-h-0"
          >
            Thêm account
          </button>
        }
      />

      <ChannelSettingsPanel />

      {notice && <p className={`mb-4 text-small ${NOTICE_CLASS[notice.tone]}`}>{notice.text}</p>}

      <div className="grid gap-3 2xl:grid-cols-2">
        {accounts.length === 0 && (
          <div className="gc-card px-5 py-10 text-center text-ink-soft 2xl:col-span-2">
            Chưa có account nào - bấm &quot;Thêm account&quot;, chọn tài khoản cá nhân (quét QR)
            hoặc tài khoản bot (nhập token)
          </div>
        )}
        {accounts.map((acc) => {
          const agent = agentName(acc.agent_id);
          const status = statusBadge(acc);
          return (
            <div key={acc.id} className="gc-card flex flex-wrap items-center gap-4 px-5 py-4">
              <InitialAvatar name={acc.label} />
              <div className="min-w-0 flex-1 basis-48">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold break-words text-ink">{acc.label}</span>
                  <Badge tone="blue">{NHAN_KENH_NGAN[acc.channel]}</Badge>
                  <PolicyProfileBadge profile={acc.policy_profile} />
                  <Badge tone={status.tone}>{status.text}</Badge>
                </div>
                <div className="mt-0.5 text-label break-words text-ink-soft">
                  {acc.id} · não: {agent ? `${agent.icon} ${agent.name}` : acc.agent_id}
                </div>
              </div>

              <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto">
                <button
                  role="switch"
                  aria-checked={acc.enabled}
                  aria-label={`Bật account ${acc.label}`}
                  onClick={() => void toggleEnabled(acc)}
                  className={`relative h-11 w-11 shrink-0 rounded-full sm:h-5 sm:w-9 sm:transition-colors ${
                    acc.enabled ? "sm:bg-brand-500" : "sm:bg-ink-soft/40"
                  }`}
                  title={acc.enabled ? "Đang bật - bấm để tắt" : "Đang tắt - bấm để bật"}
                >
                  <span
                    className={`absolute top-1/2 left-1/2 h-5 w-9 -translate-x-1/2 -translate-y-1/2 rounded-full transition-colors sm:hidden ${
                      acc.enabled ? "bg-brand-500" : "bg-ink-soft/40"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 h-4 w-4 rounded-full bg-surface shadow-sm transition-all ${
                        acc.enabled ? "left-[18px]" : "left-0.5"
                      }`}
                    />
                  </span>
                  <span
                    className={`absolute top-0.5 hidden h-4 w-4 rounded-full bg-surface shadow-sm transition-all sm:block ${
                      acc.enabled ? "left-[18px]" : "left-0.5"
                    }`}
                  />
                </button>
                {/* Chỉ tài khoản cá nhân mới quét QR; tài khoản bot nhập token
                    trong drawer Sửa. Hiện nút QR cho bot là dẫn vào ngõ cụt. */}
                {acc.channel === "zalo_personal" && (
                  <button
                    onClick={() => setQrAccount(acc)}
                    className="min-h-11 rounded-control border border-line px-3 py-1.5 text-small font-medium text-brand-600 hover:bg-brand-50 sm:min-h-0"
                  >
                    Login QR
                  </button>
                )}
                <button
                  onClick={() => setEditing(acc)}
                  className="min-h-11 rounded-control border border-line px-3 py-1.5 text-small font-medium text-ink hover:bg-tile sm:min-h-0"
                >
                  Sửa
                </button>
                <button
                  onClick={() => void remove(acc)}
                  className="min-h-11 rounded-control px-3 py-1.5 text-small text-danger hover:bg-danger-soft sm:min-h-0"
                >
                  Xóa
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {(editing || creating) && (
        <AccountEditDrawer
          account={editing}
          agents={agents}
          onClose={closeDrawer}
          onSaved={onSaved}
        />
      )}

      {qrAccount && <QrLoginModal account={qrAccount} onClose={closeQr} />}

      {confirmDialog}
    </div>
  );
}
