/** Everyone who wrote to an account, answered or not; let them into an account's list of recipients here. */
import { useEffect, useState } from "react";

import { messageOf, zalo } from "../client";
import { toggledIds, when } from "../logic";
import { AccountPicker, useAccounts } from "../parts";
import { ui } from "../sdk";
import type { Account, Contact } from "../types";

const PAGE_SIZE = 50;
const SEARCH_DELAY_MS = 300;

export function ContactsPage() {
  const { accounts, error: accountsError, reload: reloadAccounts } = useAccounts();
  const [accountId, setAccountId] = useState("");
  const [typed, setTyped] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Contact[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(typed.trim());
      setPage(0);
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [typed]);

  useEffect(() => {
    let stale = false;
    // One row more than a page tells whether a next page exists.
    zalo.contacts({ account_id: accountId || undefined, q: query, limit: PAGE_SIZE + 1, offset: page * PAGE_SIZE }).then(
      (found) => {
        if (stale) return;
        setRows(found.slice(0, PAGE_SIZE));
        setHasMore(found.length > PAGE_SIZE);
        setError("");
      },
      (err: unknown) => !stale && setError(messageOf(err)),
    );
    return () => {
      stale = true;
    };
  }, [accountId, query, page, version]);

  async function remove(contact: Contact) {
    const who = contact.display_name || contact.user_id;
    if (!window.confirm(`Xóa "${who}" khỏi danh bạ? Lịch sử trò chuyện vẫn giữ; người này nhắn lại sẽ hiện lại.`)) return;
    try {
      await zalo.deleteContact(contact.account_id, contact.user_id);
      setVersion((v) => v + 1);
    } catch (err) {
      setError(messageOf(err));
    }
  }

  async function allow(account: Account, uid: string, allowed: boolean) {
    try {
      await zalo.update(account.id, {
        allowlist: { mode: account.allowlist.mode, user_ids: toggledIds(account.allowlist.user_ids, uid, allowed) },
      });
      await reloadAccounts();
    } catch (err) {
      setError(messageOf(err));
    }
  }

  const byId = new Map((accounts ?? []).map((a) => [a.id, a]));
  return (
    <div>
      <ui.PageHeader
        title="Danh bạ Zalo"
        subtitle="Tự ghi từ mọi tin nhắn tới, kể cả người agent không trả lời. Bật để đưa họ vào danh sách được trả lời."
      />
      {(error || accountsError) && <ui.Notice tone="danger">{error || accountsError}</ui.Notice>}
      <div className="my-4 grid gap-3 sm:grid-cols-[1fr_16rem]">
        <ui.Input
          type="search"
          aria-label="Tìm"
          placeholder="Tìm theo tên hoặc user ID..."
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <AccountPicker
          accounts={accounts ?? []}
          value={accountId}
          all="Mọi tài khoản"
          onChange={(id) => {
            setAccountId(id);
            setPage(0);
          }}
        />
      </div>
      <ui.Card>
        {rows.length === 0 ? (
          <ui.Empty>Chưa có ai.</ui.Empty>
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((contact) => (
              <ContactRow
                key={`${contact.account_id}:${contact.user_id}`}
                contact={contact}
                account={byId.get(contact.account_id)}
                onAllow={allow}
                onRemove={remove}
              />
            ))}
          </ul>
        )}
      </ui.Card>
      <div className="mt-4 flex items-center justify-end gap-2">
        <ui.Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>
          Trước
        </ui.Button>
        <span className="text-small text-ink-soft">Trang {page + 1}</span>
        <ui.Button variant="secondary" disabled={!hasMore} onClick={() => setPage(page + 1)}>
          Sau
        </ui.Button>
      </div>
    </div>
  );
}

function ContactRow({
  contact,
  account,
  onAllow,
  onRemove,
}: {
  contact: Contact;
  account: Account | undefined;
  onAllow: (account: Account, uid: string, allowed: boolean) => Promise<void>;
  onRemove: (contact: Contact) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const listed = account?.allowlist.user_ids.includes(contact.user_id) ?? false;

  async function toggle(allowed: boolean) {
    if (!account) return;
    setBusy(true);
    await onAllow(account, contact.user_id, allowed);
    setBusy(false);
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="font-medium break-words text-ink">{contact.display_name || "(không tên)"}</p>
        <p className="text-label break-all text-ink-soft">
          <span className="font-mono">{contact.user_id}</span> · {account?.label ?? contact.account_id} ·{" "}
          {contact.message_count} tin · gần nhất {when(contact.last_seen)}
        </p>
      </div>
      <div className="flex items-center gap-3">
        {account?.allowlist.mode === "all" ? (
          <ui.Badge tone="success">Trả lời mọi người</ui.Badge>
        ) : (
          account && (
            <div className="flex items-center gap-2 text-small text-ink-soft">
              {listed ? "Được trả lời" : "Không trả lời"}
              <ui.Toggle
                checked={listed}
                disabled={busy}
                label={`Trả lời ${contact.display_name || contact.user_id}`}
                onChange={(on) => void toggle(on)}
              />
            </div>
          )
        )}
        <a
          href={`/admin/agent/sessions?q=${encodeURIComponent(contact.user_id)}`}
          className="text-small font-medium text-link hover:underline"
        >
          Xem phiên chat
        </a>
        <ui.Button variant="ghost" onClick={() => void onRemove(contact)}>
          Xóa
        </ui.Button>
      </div>
    </li>
  );
}
