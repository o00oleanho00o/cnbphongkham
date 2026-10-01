// ported from: web/src/pages/sessions-page.tsx
"use client";

// Deviations: `accounts` from the shell context; the list endpoints return a bare array with
// limit/offset (no `hasMore`), so one extra row is requested and its presence is "has a next page".
// `ThreadRow` has no token usage, so the "Token" column is gone (usage lives on the overview page).

import { useCallback, useEffect, useState } from "react";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type ThreadItem = Schemas["ThreadRow"];

const PAGE_SIZE = 50;
import { PageHeader } from "@/components/admin/layout/page-header";
import { IconChat, IconTrash } from "@/components/admin/shared/dashboard-icons";
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
import { SessionDetailDrawer } from "@/components/admin/traces/session-detail-drawer";

export default function SessionsPage() {
  const { accounts } = useAdminAccounts();
  const [error, setError] = useState("");
  const [items, setItems] = useState<ThreadItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [page, setPage] = useState(0);
  const [openThread, setOpenThread] = useState<ThreadItem | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const showAccountColumn = accounts.length > 1;

  const reload = useCallback(() => {
    unwrap(
      http.GET("/api/v1/admin/threads", {
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

  async function toggleBot(t: ThreadItem) {
    await unwrap(
      http.PATCH("/api/v1/admin/threads/{account_id}/{thread_id}", {
        params: { path: { account_id: t.account_id, thread_id: t.thread_id } },
        body: { bot_enabled: !t.bot_enabled },
      }),
    ).catch((e: unknown) => setError(errorMessage(e)));
    reload();
  }

  async function xoa(t: ThreadItem) {
    const ok = await confirm({
      title: `Xóa cuộc trò chuyện "${t.display_name || t.thread_id}"?`,
      message: `Xóa hẳn session này và toàn bộ ${formatNumber(t.message_count)} tin nhắn. Danh bạ vẫn được giữ. Không hoàn tác được.`,
      confirmLabel: "Xóa session",
    });
    if (!ok) return;
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/threads/{account_id}/{thread_id}", {
          params: { path: { account_id: t.account_id, thread_id: t.thread_id } },
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      if (
        openThread &&
        openThread.thread_id === t.thread_id &&
        openThread.account_id === t.account_id
      ) {
        setOpenThread(null);
      }
      reload();
    }
  }

  return (
    <div>
      <PageHeader
        icon={IconChat}
        title="Phiên chat AI"
        subtitle="Mỗi cuộc trò chuyện (chat riêng hoặc nhóm) là một phiên; ngữ cảnh trò chuyện của trợ lý AI giữ ở đây. Có thể chứa dữ liệu bệnh nhân: chỉ nhân viên được phân quyền xem."
      />

      {error && (
        <p role="alert" className="mb-3 text-[13px] text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <ListToolbar
        query={query}
        onQuery={setQuery}
        placeholder="Tìm theo tên hoặc thread ID..."
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
            ? ["Tên", "Account", "Loại", "Tin nhắn", "Tin cuối", "Bot", ""]
            : ["Tên", "Loại", "Tin nhắn", "Tin cuối", "Bot", ""]
        }
        minWidth={showAccountColumn ? 960 : 860}
      >
        {items.length === 0 && (
          <EmptyRow colSpan={showAccountColumn ? 7 : 6} text="Chưa có session nào" />
        )}
        {items.map((t) => (
          <tr
            key={`${t.account_id}:${t.thread_id}`}
            className="border-b border-line/60 last:border-0 hover:bg-tile/40"
          >
            <td className="px-4 py-3">
              <div className="flex items-center gap-3">
                <InitialAvatar name={t.display_name || t.thread_id} />
                <div className="min-w-0">
                  <div className="truncate font-medium text-ink">
                    {t.display_name || t.thread_id}
                  </div>
                  <div className="truncate text-[12px] text-ink-soft/60">{t.thread_id}</div>
                </div>
              </div>
            </td>
            {showAccountColumn && (
              <td className="px-4 py-3">
                <Badge tone="gray" dot={false}>
                  {accountLabel(accounts, t.account_id)}
                </Badge>
              </td>
            )}
            <td className="px-4 py-3">
              <Badge tone={t.thread_type === 1 ? "amber" : "blue"} dot={false}>
                {t.thread_type === 1 ? "Nhóm" : "Chat riêng"}
              </Badge>
            </td>
            <td className="px-4 py-3 text-ink-soft">{formatNumber(t.message_count)}</td>
            <td className="px-4 py-3 text-ink-soft">{formatTime(t.last_message_at)}</td>
            <td className="px-4 py-3">
              <button
                onClick={() => toggleBot(t)}
                className={`relative h-5 w-9 rounded-full transition-colors ${
                  t.bot_enabled ? "bg-brand-500" : "bg-slate-300 dark:bg-slate-600"
                }`}
                title={t.bot_enabled ? "Bot đang bật - bấm để tắt" : "Bot đang tắt - bấm để bật"}
              >
                <span
                  className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all ${
                    t.bot_enabled ? "left-[18px]" : "left-0.5"
                  }`}
                />
              </button>
            </td>
            <td className="px-4 py-3">
              <div className="flex items-center justify-end gap-1">
                <button
                  onClick={() => setOpenThread(t)}
                  className="text-[13px] font-medium text-brand-600 hover:underline"
                >
                  Xem
                </button>
                <button
                  onClick={() => xoa(t)}
                  className="rounded-lg p-1.5 text-ink-soft/60 transition-colors hover:bg-red-500/10 hover:text-red-500"
                  title="Xóa hẳn session này"
                >
                  <IconTrash className="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        ))}
      </TableShell>

      {openThread && (
        <SessionDetailDrawer
          thread={openThread}
          onClose={() => setOpenThread(null)}
          onDoiDuLieu={reload}
        />
      )}

      {confirmDialog}
    </div>
  );
}
