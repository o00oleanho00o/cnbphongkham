/** The groups the accounts are in, by the names last seen. */
import { useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { AccountPicker, useAccounts } from "../parts";
import { ui } from "../sdk";
import type { Group } from "../types";

export function GroupsPage() {
  const { accounts } = useAccounts();
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

  const labels = new Map((accounts ?? []).map((a) => [a.id, a.label]));
  return (
    <div>
      <ui.PageHeader title="Nhóm Zalo" subtitle="Nhóm mà các tài khoản đã nhận tin, theo tên thấy gần nhất" />
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <div className="mb-4 sm:max-w-sm">
        <AccountPicker accounts={accounts ?? []} value={accountId} all="Mọi tài khoản" onChange={setAccountId} />
      </div>
      <ui.Card>
        {groups?.length === 0 && <ui.Empty>Chưa có nhóm nào.</ui.Empty>}
        <ul className="divide-y divide-line">
          {groups?.map((g) => (
            <li key={`${g.account_id}:${g.thread_id}`} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <span className="font-medium break-words text-ink">{g.name || "(không tên)"}</span>
              <span className="text-label break-all text-ink-soft">
                <span className="font-mono">{g.thread_id}</span> · {labels.get(g.account_id) ?? g.account_id}
              </span>
            </li>
          ))}
        </ul>
      </ui.Card>
    </div>
  );
}
