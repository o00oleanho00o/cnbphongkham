/** Friend requests and friends of a personal account (the Bot API has neither). */
import { useCallback, useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { when } from "../logic";
import { AccountPicker, useAccounts } from "../parts";
import { ui } from "../sdk";
import type { Friend, FriendRequest } from "../types";

const REQUESTS_POLL_MS = 7000;

export function FriendsPage() {
  const { accounts, error } = useAccounts();
  const personal = (accounts ?? []).filter((a) => a.channel === "zalo_personal");
  const [picked, setPicked] = useState("");
  const accountId = personal.some((a) => a.id === picked) ? picked : (personal[0]?.id ?? "");

  return (
    <div>
      <ui.PageHeader title="Bạn bè Zalo" subtitle="Duyệt lời mời kết bạn và xem bạn bè của nick cá nhân đang chạy" />
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {accounts && personal.length === 0 && <ui.Empty>Chưa có nick cá nhân nào. Bot chính thức không có bạn bè.</ui.Empty>}
      {accountId && (
        <>
          <div className="mb-4 sm:max-w-sm">
            <AccountPicker accounts={personal} value={accountId} onChange={setPicked} />
          </div>
          <Requests key={`r-${accountId}`} accountId={accountId} />
          <Friends key={`f-${accountId}`} accountId={accountId} />
        </>
      )}
    </div>
  );
}

function Requests({ accountId }: { accountId: string }) {
  const [requests, setRequests] = useState<FriendRequest[]>([]);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    zalo.friendRequests(accountId).then(setRequests, () => setRequests([]));
  }, [accountId]);

  useEffect(() => {
    reload();
    const timer = setInterval(reload, REQUESTS_POLL_MS);
    return () => clearInterval(timer);
  }, [reload]);

  async function decide(request: FriendRequest, accept: boolean) {
    const who = request.sender_name || request.from_uid;
    if (!accept && !window.confirm(`Từ chối lời mời của "${who}"?`)) return;
    setError("");
    try {
      await zalo.decide(accountId, request.from_uid, accept);
    } catch (err) {
      setError(`${accept ? "Không chấp nhận" : "Không từ chối"} được "${who}": ${messageOf(err)}`);
    } finally {
      reload();
    }
  }

  return (
    <div className="mb-6">
      <ui.Card title={`Chờ duyệt (${requests.length})`}>
        <p className="mb-3 text-label text-ink-soft">
          Chỉ có lời mời tới từ khi nick đang chạy - Zalo không cho lấy lại lời mời cũ.
        </p>
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
        {requests.length === 0 ? (
          <ui.Empty>Không có lời mời nào đang chờ.</ui.Empty>
        ) : (
          <ul className="divide-y divide-line">
            {requests.map((r) => (
              <li key={r.from_uid} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="font-medium break-words text-ink">{r.sender_name || r.from_uid}</p>
                  <p className="text-label break-words text-ink-soft">
                    {r.message || "Không có lời nhắn"} · {when(r.received_at)}
                  </p>
                </div>
                <div className="flex gap-2">
                  <ui.Button onClick={() => void decide(r, true)}>Chấp nhận</ui.Button>
                  <ui.Button variant="secondary" onClick={() => void decide(r, false)}>
                    Từ chối
                  </ui.Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </ui.Card>
    </div>
  );
}

function Friends({ accountId }: { accountId: string }) {
  const [friends, setFriends] = useState<Friend[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Asks Zalo itself, so it is not polled.
  const reload = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      setFriends(await zalo.friends(accountId));
    } catch (err) {
      setFriends([]);
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }, [accountId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <ui.Card
      title={`Bạn bè (${friends.length})`}
      aside={
        <ui.Button variant="secondary" busy={busy} onClick={() => void reload()}>
          Làm mới
        </ui.Button>
      }
    >
      {error && <ui.Notice tone="warning">{error}</ui.Notice>}
      {!error && friends.length === 0 && <ui.Empty>{busy ? "Đang tải..." : "Chưa có bạn nào."}</ui.Empty>}
      <ul className="divide-y divide-line">
        {friends.map((f) => (
          <li key={f.user_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <span className="font-medium break-words text-ink">{f.display_name || "(không tên)"}</span>
            <span className="font-mono text-label text-ink-soft">{f.user_id}</span>
          </li>
        ))}
      </ul>
    </ui.Card>
  );
}
