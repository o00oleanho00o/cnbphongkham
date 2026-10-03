// ported from: web/src/pages/contacts-page.tsx
"use client";

// Deviations: `accounts` from the shell context; the list endpoints return a bare array with
// limit/offset (no `hasMore`), so one extra row is requested and its presence is "has a next page".

import { useCallback, useEffect, useState } from "react";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type ContactItem = Schemas["ContactRow"];

const PAGE_SIZE = 50;
import { PageHeader } from "@/components/admin/layout/page-header";
import { IconTrash } from "@/components/admin/shared/dashboard-icons";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { AccountFilter, accountLabel } from "@/components/admin/shared/account-filter";
import {
  Badge,
  EmptyRow,
  formatNumber,
  formatTime,
  InitialAvatar,
  ListToolbar,
  TableShell,
} from "@/components/admin/shared/ui-bits";

export default function ContactsPage() {
  const { accounts } = useAdminAccounts();
  const [error, setError] = useState("");
  const [items, setItems] = useState<ContactItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [page, setPage] = useState(0);
  const { confirm, confirmDialog } = useConfirmDialog();

  const showAccountColumn = accounts.length > 1;

  const reload = useCallback(() => {
    unwrap(
      http.GET("/api/v1/admin/contacts", {
        params: {
          query: {
            account_id: accountFilter || undefined,
            q: query || undefined,
            limit: PAGE_SIZE + 1,
            offset: page * PAGE_SIZE,
          },
        },
      }),
    )
      .then((rows) => {
        setItems(rows.slice(0, PAGE_SIZE));
        setHasMore(rows.length > PAGE_SIZE);
        setError("");
      })
      .catch((e: unknown) => {
        setItems([]);
        setError(errorMessage(e));
      });
  }, [accountFilter, query, page]);

  useEffect(reload, [reload]);
  useEffect(() => setPage(0), [accountFilter, query]);

  async function xoa(contact: ContactItem) {
    const ok = await confirm({
      title: `Xóa danh bạ "${contact.display_name || contact.user_id}"?`,
      message:
        "Chỉ xóa khỏi danh sách danh bạ, KHÔNG đụng lịch sử chat. Người này nhắn lại thì tự hiện lại.",
      confirmLabel: "Xóa danh bạ",
    });
    if (!ok) return;
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/contacts/{account_id}/{user_id}", {
          params: { path: { account_id: contact.account_id, user_id: contact.user_id } },
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      reload();
    }
  }

  return (
    <div>
      <PageHeader
        title="Danh bạ"
        subtitle="Tự thu thập từ mọi tin nhắn đến, kể cả người trợ lý AI không trả lời"
      />

      {error && (
        <p role="alert" className="mb-3 text-small text-danger">
          {error}
        </p>
      )}

      <ListToolbar
        query={query}
        onQuery={setQuery}
        placeholder="Tìm theo tên hoặc user ID..."
        filter={
          <AccountFilter accounts={accounts} value={accountFilter} onChange={setAccountFilter} />
        }
        page={page}
        hasMore={hasMore}
        onPage={setPage}
      />

      <TableShell
        headers={
          showAccountColumn
            ? ["Tên", "Account", "User ID", "Số tin", "Lần đầu", "Gần nhất", ""]
            : ["Tên", "User ID", "Số tin", "Lần đầu", "Gần nhất", ""]
        }
        minWidth={showAccountColumn ? 900 : 800}
      >
        {items.length === 0 && (
          <EmptyRow colSpan={showAccountColumn ? 7 : 6} text="Chưa có contact nào" />
        )}
        {items.map((contact) => (
          <tr
            key={`${contact.account_id}:${contact.user_id}`}
            className="border-b border-line/60 last:border-0 hover:bg-tile/40"
          >
            <td className="px-4 py-3">
              <div className="flex items-center gap-3">
                <InitialAvatar name={contact.display_name || contact.user_id} />
                <span className="font-medium text-ink">
                  {contact.display_name || "(không tên)"}
                </span>
              </div>
            </td>
            {showAccountColumn && (
              <td className="px-4 py-3">
                <Badge tone="gray" dot={false}>
                  {accountLabel(accounts, contact.account_id)}
                </Badge>
              </td>
            )}
            <td className="px-4 py-3 text-ink-soft">{contact.user_id}</td>
            <td className="px-4 py-3 text-ink-soft">{formatNumber(contact.message_count)}</td>
            <td className="px-4 py-3 text-ink-soft">{formatTime(contact.first_seen)}</td>
            <td className="px-4 py-3 text-ink-soft">{formatTime(contact.last_seen)}</td>
            <td className="px-4 py-3 text-right">
              <button
                onClick={() => xoa(contact)}
                className="rounded-control p-1.5 text-ink-soft/60 transition-colors hover:bg-danger-soft hover:text-danger"
                title="Xóa danh bạ"
              >
                <IconTrash className="h-4 w-4" />
              </button>
            </td>
          </tr>
        ))}
      </TableShell>

      {confirmDialog}
    </div>
  );
}
