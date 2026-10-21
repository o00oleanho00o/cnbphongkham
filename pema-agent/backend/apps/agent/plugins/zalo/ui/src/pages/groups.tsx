/** The groups the accounts are in, by the names last seen; switch on the ones an account listens to. */
import { useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { toggledIds } from "../logic";
import { PagingProvider, usePaged } from "../paging";
import { AccountPicker, useAccounts } from "../parts";
import { ui } from "../sdk";
import type { Account, Group } from "../types";

export function GroupsPage() {
  const { accounts, error: accountsError, reload: reloadAccounts } = useAccounts();
  const [accountId, setAccountId] = useState("");
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stale = false;
    zalo.groups(accountId || undefined).then(
      (found) => !stale && setGroups(found),
      (err: unknown) => !stale && setError(messageOf(err)),
    );
    return () => {
      stale = true;
    };
  }, [accountId]);

  async function listen(account: Account, threadId: string, listening: boolean) {
    try {
      await zalo.update(account.id, { listen_group_ids: toggledIds(account.listen_group_ids, threadId, listening) });
      await reloadAccounts();
      setError("");
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function allow(account: Account, threadId: string, allowed: boolean) {
    try {
      await zalo.update(account.id, {
        group_allowlist: {
          mode: account.group_allowlist.mode,
          group_ids: toggledIds(account.group_allowlist.group_ids, threadId, allowed),
        },
      });
      await reloadAccounts();
      setError("");
    } catch (err) {
      setError(messageOf(err));
    }
  }

  const byId = new Map((accounts ?? []).map((a) => [a.id, a]));
  const listened = (groups ?? []).filter((g) => byId.get(g.account_id)?.listen_group_ids.includes(g.thread_id)).length;
  return (
    <PagingProvider>
      <div>
        <ui.PageHeader
          title="Nhóm Zalo"
          subtitle="Hai việc riêng cho mỗi nhóm: lắng nghe (agent ghi nhớ tin của nhóm) và, với tài khoản đặt 'chỉ trả lời nhóm trong danh sách', cho phép trả lời. Nhóm mới luôn tắt cho tới khi bạn bật."
        />
        {(error || accountsError) && <ui.Notice tone="danger">{error || accountsError}</ui.Notice>}
        <div className="mb-4 sm:max-w-sm">
          <AccountPicker accounts={accounts ?? []} value={accountId} all="Mọi tài khoản" onChange={setAccountId} />
        </div>
        <ui.Card>
          {groups?.length === 0 && (
            <ui.Empty>Chưa có nhóm nào. Một nhóm hiện ở đây sau tin nhắn đầu tiên của nhóm đó.</ui.Empty>
          )}
          {groups !== null && groups.length > 0 && (
            <GroupList groups={groups} scope={accountId} byId={byId} onListen={listen} onAllow={allow} />
          )}
        </ui.Card>
        {groups !== null && groups.length > 0 && (
          <p className="mt-3 text-label text-ink-soft">
            Đang nghe {listened}/{groups.length} nhóm. Nhóm tắt: tin không được lưu. Việc trả lời theo cài đặt của tài
            khoản: mọi nhóm, hoặc chỉ nhóm được bật "Cho trả lời".
          </p>
        )}
      </div>
    </PagingProvider>
  );
}

/** The groups of the page, five at first and five more each time the page is scrolled to the end of the list. */
function GroupList({
  groups,
  scope,
  byId,
  onListen,
  onAllow,
}: {
  groups: readonly Group[];
  scope: string;
  byId: ReadonlyMap<string, Account>;
  onListen: (account: Account, threadId: string, listening: boolean) => Promise<void>;
  onAllow: (account: Account, threadId: string, allowed: boolean) => Promise<void>;
}) {
  const { shown, hasNext, endRef } = usePaged(["groups-page", scope], groups);
  return (
    <>
      <ul className="divide-y divide-line">
        {shown.map((g) => (
          <GroupRow
            key={`${g.account_id}:${g.thread_id}`}
            group={g}
            account={byId.get(g.account_id)}
            onListen={onListen}
            onAllow={onAllow}
          />
        ))}
      </ul>
      {hasNext && (
        <div ref={endRef} className="py-3 text-center text-label text-ink-soft">
          Kéo xuống để xem thêm
        </div>
      )}
    </>
  );
}

function GroupRow({
  group,
  account,
  onListen,
  onAllow,
}: {
  group: Group;
  account: Account | undefined;
  onListen: (account: Account, threadId: string, listening: boolean) => Promise<void>;
  onAllow: (account: Account, threadId: string, allowed: boolean) => Promise<void>;
}) {
  const name = group.name || "(không tên)";
  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <span className="min-w-0">
        <span className="block font-medium break-words text-ink">{name}</span>
        <span className="block text-label break-all text-ink-soft">
          <span className="font-mono">{group.thread_id}</span> · {account?.label ?? group.account_id}
        </span>
      </span>
      {account && (
        <span className="flex items-center gap-4">
          {account.group_allowlist.mode === "list" && (
            <span className="flex items-center gap-2 text-label text-ink-soft">
              Cho trả lời
              <ui.Toggle
                checked={account.group_allowlist.group_ids.includes(group.thread_id)}
                label={`Cho trả lời trong nhóm ${name}`}
                onChange={(allowed) => void onAllow(account, group.thread_id, allowed)}
              />
            </span>
          )}
          <span className="flex items-center gap-2 text-label text-ink-soft">
            Lắng nghe
            <ui.Toggle
              checked={account.listen_group_ids.includes(group.thread_id)}
              label={`Lắng nghe nhóm ${name}`}
              onChange={(listening) => void onListen(account, group.thread_id, listening)}
            />
          </span>
        </span>
      )}
    </li>
  );
}
