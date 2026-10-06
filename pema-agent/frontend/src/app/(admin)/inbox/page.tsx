"use client";

// Inbox: conversations of patients on Zalo (`GET /api/v1/conversations`), with the thread beside the list
// on desktop and as a child screen on a phone (`?c=<id>`). Messages come from `clinic.message`, the Inbox
// of record; `agent.history` (the LLM context) is a different store and never shown here.
// Several people work here at once: `inbox.changed`, `assignment.changed` and `presence.changed` events
// (GET /api/v1/events) reload the list quietly (selection, scroll and a draft being typed stay), the open thread
// reloads when it is the one that changed, and without the stream the list refreshes every 30 seconds.
// Package O: three tabs (Chờ nhận / Của tôi / Tất cả) and an identity filter, kept in the URL so they survive a
// reload. The BE has no unassigned or identity filter on the list yet (O5 report), so the tabs and the identity
// filter work on the loaded rows (up to 100). A takeover of a thread I held shows a toast.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconSearch } from "@/components/admin/shared/dashboard-icons";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { ConversationList } from "@/components/ops/inbox/conversation-list";
import { ThreadView } from "@/components/ops/inbox/thread-view";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { LiveStatus } from "@/components/ops/live-status";
import { MasterDetail } from "@/components/ops/master-detail";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { useIdentities } from "@/lib/identities/use-identities";
import { viewersOf, type LiveEvent, type LiveEventType } from "@/lib/live/live-types";
import { useLiveEvents } from "@/lib/live/use-live-events";
import { CONVERSATION_STATUS_LABEL } from "@/lib/ops/labels";
import {
  ALL_IDENTITIES,
  ALL_IDENTITIES_LABEL,
  INBOX_TABS,
  INBOX_TAB_LABEL,
  conversationCode,
  customerIdentities,
  inboxHref,
  isInTab,
  matchesIdentity,
  readInboxParams,
  tabCounts,
  takenOver,
  type InboxTab,
} from "@/lib/ops/inbox-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Card } from "@/ui/card";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";
import { Tabs } from "@/ui/tabs";

type StatusFilter = "all" | Schemas["ConversationStatus"];

const STATUS_FILTERS: StatusFilter[] = ["all", "pending_review", "handoff", "open", "closed"];
const SEARCH_DEBOUNCE_MS = 300;
const LIVE_TYPES: readonly LiveEventType[] = [
  "inbox.changed",
  "assignment.changed",
  "presence.changed",
];

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
  const { user, can } = useSession();
  const toast = useToast();
  const { identities } = useIdentities();
  const canClaim = can("thread.claim");
  const { conversationId: selectedId, tab, identityId } = readInboxParams(params, canClaim);
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
  const { data, error, loading, reload, refresh } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);

  // Bumped when the open conversation itself changed; the thread reloads on it (see ThreadView `liveTick`).
  const [threadTick, setThreadTick] = useState(0);
  const onLiveEvent = useCallback(
    (event: LiveEvent) => {
      refresh();
      const concernsThread = event.id === null || event.id === selectedId;
      const changesThread = event.type === "inbox.changed" || event.type === "assignment.changed";
      if (changesThread && concernsThread) setThreadTick((n) => n + 1);
    },
    [refresh, selectedId],
  );
  const onLiveRefresh = useCallback(() => {
    refresh();
    setThreadTick((n) => n + 1);
  }, [refresh]);
  const liveMode = useLiveEvents({
    types: LIVE_TYPES,
    onEvent: onLiveEvent,
    onRefresh: onLiveRefresh,
  });

  // Presence of the open conversation as the (fresher) list knows it; undefined when it is not in the list.
  const viewers = useMemo(() => {
    const row = items.find((c) => c.id === selectedId);
    return row ? viewersOf(row) : undefined;
  }, [items, selectedId]);

  const open = useCallback(
    (id: string) => router.push(inboxHref({ conversationId: id, tab, identityId })),
    [router, tab, identityId],
  );
  const back = useCallback(
    () => router.push(inboxHref({ tab, identityId })),
    [router, tab, identityId],
  );
  const setTab = useCallback(
    (next: string) =>
      router.replace(inboxHref({ conversationId: selectedId, tab: next as InboxTab, identityId })),
    [router, selectedId, identityId],
  );
  const setIdentity = useCallback(
    (next: string) =>
      router.replace(inboxHref({ conversationId: selectedId, tab, identityId: next })),
    [router, selectedId, tab],
  );

  // A thread I held that a colleague holds now: tell me, once (the list is the source of who holds what).
  const holders = useRef(new Map<string, string | null>());
  useEffect(() => {
    takenOver(holders.current, items, user.id).forEach((t) =>
      toast.push("info", `Đã bị tiếp quản: ${t.byName} giữ hội thoại ${conversationCode(t.id)}.`),
    );
    holders.current = new Map(items.map((c) => [c.id, c.assigned_user_id ?? null]));
  }, [items, user.id, toast]);

  const pendingTotal = useMemo(() => items.filter((c) => c.has_pending_review).length, [items]);

  const rows = useMemo(
    () => items.filter((c) => matchesIdentity(c, identityId, identities)),
    [items, identityId, identities],
  );
  const counts = useMemo(() => tabCounts(rows, user.id), [rows, user.id]);
  const shown = useMemo(() => rows.filter((c) => isInTab(c, tab, user.id)), [rows, tab, user.id]);
  const identityOptions = useMemo<SelectOption[]>(
    () => [
      { value: ALL_IDENTITIES, label: ALL_IDENTITIES_LABEL },
      ...customerIdentities(identities).map((i) => ({ value: i.id, label: i.label })),
    ],
    [identities],
  );
  const tabItems = useMemo(
    () =>
      INBOX_TABS.map((id) => ({
        id,
        label: INBOX_TAB_LABEL[id],
        count: data ? counts[id] : undefined,
      })),
    [counts, data],
  );

  const list = (
    <Card>
      <Tabs
        label="Hàng chờ hội thoại"
        idPrefix="inbox"
        items={tabItems}
        value={tab}
        onChange={setTab}
        segmented
      />
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
            className={cx(FIELD_BASE_CLASS, "w-full pl-9")}
          />
        </div>
        {identityOptions.length > 1 && (
          <div className="sm:w-60">
            <SelectMenu
              size="md"
              ariaLabel="Lọc theo danh tính"
              value={identityId}
              options={identityOptions}
              onChange={setIdentity}
            />
          </div>
        )}
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
      {data && shown.length === 0 && <EmptyList tab={tab} />}
      <ConversationList
        items={shown}
        selectedId={selectedId}
        onOpen={open}
        meId={user.id}
        identities={identities}
      />
    </Card>
  );

  return (
    <div>
      <PageHeader
        title="Inbox"
        subtitle={`${data?.total ?? 0} hội thoại · ${pendingTotal} có nháp chờ duyệt`}
      />
      <LiveStatus mode={liveMode} />
      <MasterDetail
        list={list}
        detailOpen={selectedId !== null}
        onBack={back}
        backLabel="Danh sách hội thoại"
        detail={
          selectedId ? (
            <ThreadView
              key={selectedId}
              conversationId={selectedId}
              onChanged={reload}
              liveTick={threadTick}
              listViewers={viewers}
              identities={identities}
            />
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

/** The list is empty: the queue says what it holds, the other tabs point at the filters. */
function EmptyList({ tab }: { tab: InboxTab }) {
  if (tab === "queue") {
    return (
      <EmptyState
        title="Không có hội thoại nào đang chờ nhận"
        hint="Hội thoại mới chưa có người phụ trách sẽ hiện ở đây."
      />
    );
  }
  if (tab === "mine") {
    return (
      <EmptyState
        title="Bạn chưa phụ trách hội thoại nào"
        hint="Bấm Nhận ở một hội thoại trong tab Chờ nhận."
      />
    );
  }
  return <EmptyState title="Không có hội thoại nào" hint="Đổi bộ lọc hoặc từ khóa tìm kiếm." />;
}

export default function InboxPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={4} />}>
      <InboxContent />
    </Suspense>
  );
}
