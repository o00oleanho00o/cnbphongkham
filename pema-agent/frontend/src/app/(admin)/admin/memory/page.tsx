// ported from: web/src/pages/memory-page.tsx
"use client";

// Deviations: `accounts` from the shell context; the list endpoints return a bare array with
// limit/offset (no `hasMore`), so one extra row is requested and its presence is "has a next page".

import { useCallback, useEffect, useState } from "react";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type MemoryFactItem = Schemas["MemoryFact"];

const PAGE_SIZE = 50;
import { PageHeader } from "@/components/admin/layout/page-header";
import { AccountFilter, accountLabel } from "@/components/admin/shared/account-filter";
import {
  Badge,
  EmptyRow,
  formatTime,
  ListToolbar,
  TableShell,
} from "@/components/admin/shared/ui-bits";

export default function MemoryPage() {
  const { accounts } = useAdminAccounts();
  const [error, setError] = useState("");
  const [items, setItems] = useState<MemoryFactItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState("");
  const [page, setPage] = useState(0);

  const showAccountColumn = accounts.length > 1;

  const reload = useCallback(() => {
    unwrap(
      http.GET("/api/v1/admin/memories", {
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

  async function remove(fact: MemoryFactItem) {
    await unwrap(
      http.DELETE("/api/v1/admin/memories/{account_id}/{fact_id}", {
        params: { path: { account_id: fact.account_id, fact_id: fact.id } },
      }),
    ).catch((e: unknown) => setError(errorMessage(e)));
    reload();
  }

  return (
    <div>
      <PageHeader
        title="Trí nhớ"
        subtitle="Điều trợ lý AI ghi nhớ qua công cụ save_memory - điều học ở chat riêng không bao giờ dùng trong nhóm. Với hồ sơ Kênh bệnh nhân, nội dung từ bệnh nhân không được tự ghi nhớ."
      />

      {error && (
        <p role="alert" className="mb-3 text-small text-danger">
          {error}
        </p>
      )}

      <ListToolbar
        query={query}
        onQuery={setQuery}
        placeholder="Tìm trong nội dung hoặc subject ID..."
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
            ? ["Fact", "Account", "Về", "Học từ", "Lúc", ""]
            : ["Fact", "Về", "Học từ", "Lúc", ""]
        }
        minWidth={showAccountColumn ? 880 : 780}
      >
        {items.length === 0 && (
          <EmptyRow colSpan={showAccountColumn ? 6 : 5} text="Bot chưa ghi nhớ gì" />
        )}
        {items.map((m) => (
          <tr key={m.id} className="border-b border-line/60 last:border-0 hover:bg-tile/40">
            <td className="max-w-md px-4 py-3 text-ink">{m.content}</td>
            {showAccountColumn && (
              <td className="px-4 py-3">
                <Badge tone="gray" dot={false}>
                  {accountLabel(accounts, m.account_id)}
                </Badge>
              </td>
            )}
            <td className="px-4 py-3 text-ink-soft">{m.subject_id}</td>
            <td className="px-4 py-3">
              <Badge tone={m.learned_in_group ? "amber" : "blue"} dot={false}>
                {m.learned_in_group ? "Nhóm" : "Chat riêng"}
              </Badge>
            </td>
            <td className="px-4 py-3 text-ink-soft">{formatTime(m.created_at)}</td>
            <td className="px-4 py-3">
              <button onClick={() => remove(m)} className="text-small text-danger hover:underline">
                Xóa
              </button>
            </td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}
