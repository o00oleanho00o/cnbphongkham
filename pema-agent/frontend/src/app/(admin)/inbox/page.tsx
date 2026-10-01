"use client";

// Inbox: conversations of patients on Zalo (`GET /api/v1/conversations`), with the thread beside the list
// on desktop and as a child screen on a phone (`?c=<id>`). Messages come from `clinic.message`, the Inbox
// of record; `agent.history` (the LLM context) is a different store and never shown here.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconInbox } from "@/components/admin/shared/ops-icons";
import { IconSearch } from "@/components/admin/shared/dashboard-icons";
import { ConversationList } from "@/components/ops/inbox/conversation-list";
import { ThreadView } from "@/components/ops/inbox/thread-view";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { MasterDetail } from "@/components/ops/master-detail";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { CONVERSATION_STATUS_LABEL } from "@/lib/ops/labels";
import { useLoad } from "@/lib/use-load";

type StatusFilter = "all" | Schemas["ConversationStatus"];

const STATUS_FILTERS: StatusFilter[] = ["all", "pending_review", "handoff", "open", "closed"];
const SEARCH_DEBOUNCE_MS = 300;

function useDebounced(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function InboxContent() {
  const router = useRouter();
  const params = useSearchParams();
  const selectedId = params.get("c");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), SEARCH_DEBOUNCE_MS);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/conversations", {
          params: {
            query: {
              conversation_status: status === "all" ? undefined : status,
              q: q || undefined,
              limit: 100,
            },
          },
          signal,
        }),
      ),
    [status, q],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  const open = useCallback((id: string) => router.push(`/inbox?c=${id}`), [router]);
  const back = useCallback(() => router.push("/inbox"), [router]);

  const pendingTotal = useMemo(() => items.filter((c) => c.has_pending_review).length, [items]);

  const list = (
    <div>
      <div className="mb-3 space-y-3">
        <div className="relative">
          <IconSearch
            size={15}
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-soft/60"
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Tìm hội thoại"
            placeholder="Tìm theo tên, mã hồ sơ hoặc nội dung"
            className="gc-input w-full pl-9"
          />
        </div>
        <ChipRow label="Trạng thái hội thoại">
          {STATUS_FILTERS.map((s) => (
            <FilterChip key={s} selected={status === s} onClick={() => setStatus(s)}>
              {s === "all" ? "Tất cả" : CONVERSATION_STATUS_LABEL[s]}
            </FilterChip>
          ))}
        </ChipRow>
      </div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={5} />}
      {data && items.length === 0 && (
        <EmptyState title="Không có hội thoại nào" hint="Đổi bộ lọc hoặc từ khóa tìm kiếm." />
      )}
      <ConversationList items={items} selectedId={selectedId} onOpen={open} />
    </div>
  );

  return (
    <div className="mx-auto max-w-[1600px]">
      <PageHeader
        icon={IconInbox}
        title="Inbox"
        subtitle={`${data?.total ?? 0} hội thoại · ${pendingTotal} có nháp chờ duyệt`}
      />
      <MasterDetail
        list={list}
        detailOpen={selectedId !== null}
        onBack={back}
        backLabel="Danh sách hội thoại"
        detail={
          selectedId ? (
            <ThreadView key={selectedId} conversationId={selectedId} onChanged={reload} />
          ) : null
        }
        emptyDetail={
          <EmptyState
            title="Chọn một hội thoại"
            hint="Tin khách gửi, nháp của trợ lý AI và ảnh khách gửi được gắn cờ chuyển nhân viên hiện ở đây."
          />
        }
      />
    </div>
  );
}

export default function InboxPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <InboxContent />
    </Suspense>
  );
}
