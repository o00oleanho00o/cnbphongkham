// ported from: web/src/pages/friends-page.tsx
"use client";

// Deviations: `accounts` comes from `AccountsProvider` (the shell) instead of a prop and is limited to
// personal Zalo accounts (the contract's `channel`), the typed client replaces `api.*`, `received_at` is an
// ISO string instead of epoch milliseconds, and the console logging of errors is gone (the message the
// person sees is the only trace; never log a friend's name).
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { IconCheck, IconClose } from "@/components/admin/shared/dashboard-icons";
import { SelectMenu } from "@/components/admin/shared/select-menu";
import { EmptyRow, InitialAvatar, TableShell } from "@/components/admin/shared/ui-bits";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Schemas } from "@/lib/api";
import { ApiError, http, unwrap } from "@/lib/api/client";

type FriendItem = Schemas["FriendOut"];
type FriendRequestItem = Schemas["FriendRequestOut"];

function friendName(f: FriendItem): string {
  return f.display_name || f.user_id;
}

function thoiGian(iso: string): string {
  try {
    return new Date(iso).toLocaleString("vi-VN");
  } catch {
    return "";
  }
}

export default function FriendsPage() {
  const { accounts: allAccounts } = useAdminAccounts();
  // Friends exist on personal accounts only (the Bot API has no friend list)
  const accounts = useMemo(
    () => allAccounts.filter((a) => a.channel === "zalo_personal"),
    [allAccounts],
  );
  const [picked, setPicked] = useState("");
  const accountId = picked || accounts[0]?.id || "";
  const [requests, setRequests] = useState<FriendRequestItem[]>([]);
  const [friends, setFriends] = useState<FriendItem[]>([]);
  const [friendsError, setFriendsError] = useState<string | null>(null);
  const [loadingFriends, setLoadingFriends] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const reloadRequests = useCallback(() => {
    if (!accountId) return setRequests([]);
    unwrap(
      http.GET("/api/v1/admin/friends/{account_id}/requests", {
        params: { path: { account_id: accountId } },
      }),
    )
      .then(setRequests)
      .catch(() => setRequests([]));
  }, [accountId]);

  const reloadFriends = useCallback(() => {
    if (!accountId) {
      setFriends([]);
      setFriendsError(null);
      return;
    }
    setLoadingFriends(true);
    setFriendsError(null);
    unwrap(
      http.GET("/api/v1/admin/friends/{account_id}/list", {
        params: { path: { account_id: accountId } },
      }),
    )
      .then(setFriends)
      .catch((e: unknown) => {
        setFriends([]);
        setFriendsError(
          e instanceof ApiError && e.status === 409
            ? "Tài khoản chưa chạy hoặc là kênh bot - tính năng bạn bè chỉ dùng cho nick cá nhân đang chạy."
            : "Không lấy được danh sách bạn (nguồn có thể đang giới hạn) - thử lại sau.",
        );
      })
      .finally(() => setLoadingFriends(false));
  }, [accountId]);

  useEffect(reloadRequests, [reloadRequests]);
  useEffect(reloadFriends, [reloadFriends]);
  // Đổi account thì bỏ banner lỗi hành động của account trước (đừng để dính).
  useEffect(() => setActionError(null), [accountId]);

  // Poll request mới (chỉ đọc DB nên rẻ). Danh sách bạn KHÔNG poll (gọi mạng).
  useEffect(() => {
    if (!accountId) return;
    const t = setInterval(reloadRequests, 7000);
    return () => clearInterval(t);
  }, [accountId, reloadRequests]);

  async function decide(r: FriendRequestItem, action: "accept" | "reject") {
    setActionError(null);
    const path = { account_id: accountId };
    const body = { uid: r.from_uid };
    try {
      if (action === "accept") {
        await unwrap(
          http.POST("/api/v1/admin/friends/{account_id}/accept", { params: { path }, body }),
        );
      } else {
        await unwrap(
          http.POST("/api/v1/admin/friends/{account_id}/reject", { params: { path }, body }),
        );
      }
    } catch {
      const who = r.sender_name || r.from_uid;
      setActionError(
        action === "accept"
          ? `Không chấp nhận được "${who}" - nguồn có thể đang giới hạn, thử lại sau.`
          : `Không từ chối được "${who}" - thử lại sau.`,
      );
    } finally {
      reloadRequests();
    }
  }

  async function reject(r: FriendRequestItem) {
    const ok = await confirm({
      title: `Từ chối kết bạn từ "${r.sender_name || r.from_uid}"?`,
      message: "Yêu cầu sẽ bị xóa khỏi danh sách chờ.",
      confirmLabel: "Từ chối",
    });
    if (!ok) return;
    await decide(r, "reject");
  }

  return (
    <div>
      <PageHeader
        title="Bạn bè"
        subtitle="Duyệt yêu cầu kết bạn và xem danh sách bạn (chỉ nick cá nhân đang chạy)"
      />

      {accounts.length === 0 && (
        <p className="mb-4 text-body text-ink-soft">
          Chưa có tài khoản Zalo cá nhân nào. Tính năng bạn bè không áp dụng cho kênh bot.
        </p>
      )}

      <div className="mb-4 flex items-center gap-3 sm:max-w-sm">
        <SelectMenu
          size="md"
          value={accountId}
          onChange={setPicked}
          ariaLabel="Chọn tài khoản"
          options={accounts.map((a) => ({
            value: a.id,
            label: a.label,
            dotClass: a.online ? "bg-success" : "bg-ink-soft/40",
          }))}
        />
      </div>

      <p className="mb-3 text-body text-ink-soft/80">
        Chỉ hiện yêu cầu tới TỪ KHI bật tính năng và bot đang chạy - Zalo không cho lấy lại yêu cầu
        cũ.
      </p>

      <h2 className="mb-2 text-body font-semibold text-ink">Chờ duyệt ({requests.length})</h2>
      {actionError && (
        <p role="alert" className="mb-2 text-body text-danger">
          {actionError}
        </p>
      )}
      <TableShell headers={["", "Tên", "Lời nhắn", "Nhận lúc", ""]} minWidth={700}>
        {requests.length === 0 && <EmptyRow colSpan={5} text="Không có yêu cầu nào đang chờ" />}
        {requests.map((r) => (
          <tr key={r.from_uid} className="border-b border-line/60 last:border-0 hover:bg-tile/40">
            <td className="px-4 py-3">
              <InitialAvatar name={r.sender_name || r.from_uid} />
            </td>
            <td className="px-4 py-3 font-medium text-ink">{r.sender_name || r.from_uid}</td>
            <td className="px-4 py-3 text-ink-soft">{r.message || "-"}</td>
            <td className="px-4 py-3 text-ink-soft">{thoiGian(r.received_at)}</td>
            <td className="px-4 py-3 text-right">
              <div className="flex justify-end gap-1.5">
                <button
                  onClick={() => void decide(r, "accept")}
                  className="rounded-control p-2 text-success transition-colors hover:bg-success-soft"
                  title="Chấp nhận"
                  aria-label="Chấp nhận"
                >
                  <IconCheck className="h-4 w-4" />
                </button>
                <button
                  onClick={() => void reject(r)}
                  className="rounded-control p-2 text-ink-soft/60 transition-colors hover:bg-danger-soft hover:text-danger"
                  title="Từ chối"
                  aria-label="Từ chối"
                >
                  <IconClose className="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      <div className="mt-6 mb-2 flex items-center justify-between">
        <h2 className="text-body font-semibold text-ink">Danh sách bạn ({friends.length})</h2>
        <button
          onClick={reloadFriends}
          disabled={loadingFriends}
          className="rounded-control border border-line px-3 py-1 text-body text-ink-soft transition-colors hover:bg-tile/60 disabled:opacity-50"
        >
          {loadingFriends ? "Đang tải..." : "Làm mới"}
        </button>
      </div>
      {friendsError && <p className="mb-3 text-body text-danger">{friendsError}</p>}
      <TableShell headers={["", "Tên", "User ID"]} minWidth={600}>
        {friends.length === 0 && !friendsError && (
          <EmptyRow colSpan={3} text={loadingFriends ? "Đang tải..." : "Chưa có bạn nào"} />
        )}
        {friends.map((f) => (
          <tr key={f.user_id} className="border-b border-line/60 last:border-0 hover:bg-tile/40">
            <td className="px-4 py-3">
              <InitialAvatar name={friendName(f)} />
            </td>
            <td className="px-4 py-3 font-medium text-ink">{friendName(f)}</td>
            <td className="px-4 py-3 text-ink-soft">{f.user_id}</td>
          </tr>
        ))}
      </TableShell>

      {confirmDialog}
    </div>
  );
}
