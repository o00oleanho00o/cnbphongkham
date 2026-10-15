"use client";

// Phiên chat của agent: every conversation the agent had, whatever channel it came from (Zalo, HTTP...), newest first,
// with a search, a channel filter and paging; a row opens the messages of the chat, where the chat can be deleted (the
// agent then starts that conversation from nothing) or its trace opened. Ticked rows are deleted together.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { EmptyRow, formatTime, ListToolbar, TableShell } from "@/components/admin/shared/ui-bits";
import { Badge, Empty, Notice, PageHeader, Select } from "@/components/agent/plugin-kit";
import { usePersonNames } from "@/components/agent/use-person-names";
import {
  formatCount,
  listPath,
  type Paged,
  personKey,
  type SessionDetail,
  type SessionRow,
  SESSIONS_PATH,
  sessionTitle,
  tracesOfSessionHref,
} from "@/lib/agent/activity";
import { agentApi as api } from "@/lib/agent/api";
import { Button, buttonClass } from "@/ui/button";
import { Sheet } from "@/ui/dialog";

const ALL_CHANNELS = "";

export function SessionsPage() {
  const params = useSearchParams();
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [channel, setChannel] = useState(ALL_CHANNELS);
  const [channels, setChannels] = useState<string[]>([]);
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState<string | null>(params.get("session"));
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [removing, setRemoving] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();
  const names = usePersonNames(rows);

  const reload = useCallback(async () => {
    try {
      const listing = await api.get<Paged<SessionRow>>(
        listPath(SESSIONS_PATH, { channel, q: query.trim(), page }),
      );
      setRows(listing.items);
      setHasMore(listing.has_more);
      setSelected([]);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, [channel, query, page]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    api
      .get<{ channels: { name: string }[] }>("/v1/admin/channels")
      .then((answer) => setChannels(answer.channels.map((c) => c.name)))
      .catch(() => setChannels([]));
  }, []);

  const allSelected = rows.length > 0 && selected.length === rows.length;

  function toggle(sessionId: string) {
    setSelected((now) =>
      now.includes(sessionId) ? now.filter((id) => id !== sessionId) : [...now, sessionId],
    );
  }

  async function removeSelected() {
    const ok = await confirm({
      title: `Xóa ${selected.length} phiên chat đã chọn?`,
      message:
        "Xóa hẳn tin nhắn của các phiên này để agent quên chúng: tin kế tiếp của mỗi người được trả lời như một cuộc trò chuyện mới. Trace vẫn được giữ. Không hoàn tác được.",
      confirmLabel: `Xóa ${selected.length} phiên`,
    });
    if (!ok) return;
    setRemoving(true);
    try {
      await api.post(`${SESSIONS_PATH}/delete`, { session_ids: selected });
      setOpenId((now) => (now !== null && selected.includes(now) ? null : now));
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xóa được");
    } finally {
      setRemoving(false);
    }
  }

  const openRow = rows.find((row) => row.session_id === openId);
  const openName = openRow ? names.get(personKey(openRow.channel, openRow.user_id)) : undefined;

  return (
    <div>
      <PageHeader
        title="Phiên chat"
        subtitle="Mỗi cuộc trò chuyện của agent với một người là một phiên, ở mọi kênh"
      />
      {error && <Notice tone="danger">{error}</Notice>}
      <ListToolbar
        query={query}
        onQuery={(next) => {
          setQuery(next);
          setPage(0);
        }}
        placeholder="Tìm theo người hoặc mã phiên..."
        filter={
          <Select
            aria-label="Lọc theo kênh"
            value={channel}
            onChange={(e) => {
              setChannel(e.target.value);
              setPage(0);
            }}
            options={[
              { value: ALL_CHANNELS, label: "Mọi kênh" },
              ...channels.map((name) => ({ value: name, label: name })),
            ]}
          />
        }
        page={page}
        hasMore={hasMore}
        onPage={setPage}
      />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <label className="flex min-h-11 items-center gap-2 text-small text-ink">
          <input
            type="checkbox"
            className="size-4"
            checked={allSelected}
            disabled={rows.length === 0}
            onChange={() => setSelected(allSelected ? [] : rows.map((row) => row.session_id))}
          />
          Chọn cả trang
        </label>
        <Button
          variant="danger"
          disabled={removing || selected.length === 0}
          onClick={() => void removeSelected()}
        >
          {selected.length === 0 ? "Xóa các phiên đã chọn" : `Xóa ${selected.length} phiên đã chọn`}
        </Button>
      </div>
      <TableShell headers={["", "Người", "Kênh", "Tin nhắn", "Cập nhật", ""]} minWidth={760}>
        {rows.length === 0 && <EmptyRow colSpan={6} text="Chưa có phiên chat nào" />}
        {rows.map((row) => (
          <tr
            key={row.session_id}
            className="border-b border-line/60 last:border-0 hover:bg-row-hover"
          >
            <td className="w-10 px-4 py-3">
              <input
                type="checkbox"
                className="size-4"
                aria-label={`Chọn phiên của ${sessionTitle(row)}`}
                checked={selected.includes(row.session_id)}
                onChange={() => toggle(row.session_id)}
              />
            </td>
            <td className="px-4 py-3">
              <div className="truncate font-medium text-ink">
                {names.get(personKey(row.channel, row.user_id)) ?? sessionTitle(row)}
              </div>
              <div className="truncate text-label text-ink-soft">
                {names.has(personKey(row.channel, row.user_id)) && `${row.user_id} · `}
                {row.session_id}
              </div>
            </td>
            <td className="px-4 py-3">
              {row.channel ? (
                <Badge>{row.channel}</Badge>
              ) : (
                <span className="text-ink-soft">-</span>
              )}
            </td>
            <td className="px-4 py-3 text-ink-soft">
              {formatCount(row.message_count)}
              {row.compacted && <span className="ml-1 text-label">(đã rút gọn)</span>}
            </td>
            <td className="px-4 py-3 text-ink-soft">{formatTime(row.updated_at)}</td>
            <td className="px-4 py-3 text-right">
              <Button
                variant="quiet"
                aria-label={`Xem phiên của ${sessionTitle(row)}`}
                onClick={() => setOpenId(row.session_id)}
              >
                Xem
              </Button>
            </td>
          </tr>
        ))}
      </TableShell>
      {openId && (
        <SessionSheet
          sessionId={openId}
          name={openName}
          onClose={() => setOpenId(null)}
          onDeleted={() => {
            setOpenId(null);
            void reload();
          }}
        />
      )}
      {confirmDialog}
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = { user: "Người dùng", assistant: "Agent" };

function SessionSheet({
  sessionId,
  name,
  onClose,
  onDeleted,
}: {
  sessionId: string;
  name?: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [session, setSession] = useState<SessionDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { confirm, confirmDialog } = useConfirmDialog();

  useEffect(() => {
    let stale = false;
    api
      .get<SessionDetail>(`${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`)
      .then((found) => {
        if (!stale) setSession(found);
      })
      .catch((err: unknown) => {
        if (!stale) setError(err instanceof Error ? err.message : "Không tải được");
      });
    return () => {
      stale = true;
    };
  }, [sessionId]);

  async function remove() {
    const ok = await confirm({
      title: "Xóa phiên chat này?",
      message:
        "Xóa hẳn các tin nhắn của phiên. Agent sẽ trả lời tin kế tiếp như một cuộc trò chuyện mới. Trace vẫn được giữ. Không hoàn tác được.",
      confirmLabel: "Xóa phiên",
    });
    if (!ok) return;
    setBusy(true);
    try {
      await api.del(`${SESSIONS_PATH}/${encodeURIComponent(sessionId)}`);
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xóa được");
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={name ?? (session ? sessionTitle(session) : "Phiên chat")}
      subtitle={sessionId}
      onClose={onClose}
      wide
      footer={
        <>
          <Link href={tracesOfSessionHref(sessionId)} className={buttonClass("secondary")}>
            Xem trace của phiên
          </Link>
          <Button variant="danger" disabled={busy || !session} onClick={() => void remove()}>
            Xóa phiên
          </Button>
        </>
      }
    >
      {error && <Notice tone="danger">{error}</Notice>}
      {!session && !error && <p className="text-small text-ink-soft">Đang tải...</p>}
      {session?.summary && (
        <div className="mb-3">
          <Notice>
            <b>Tóm tắt phần đầu cuộc trò chuyện (đã rút gọn):</b> {session.summary}
          </Notice>
        </div>
      )}
      {session && session.messages.length === 0 && <Empty>Phiên này chưa có tin nhắn.</Empty>}
      <ol className="space-y-3">
        {session?.messages.map((message, index) => (
          <li key={index} className="rounded-tile border border-line p-3">
            <div className="mb-1 flex flex-wrap items-center gap-2 text-label text-ink-soft">
              <b className="text-ink">{ROLE_LABEL[message.role] ?? message.role}</b>
              <span>{formatTime(message.at)}</span>
              {message.tools.map((tool) => (
                <Badge key={tool} tone="info">
                  {tool}
                </Badge>
              ))}
            </div>
            {message.text && (
              <p className="text-body break-words whitespace-pre-wrap">{message.text}</p>
            )}
          </li>
        ))}
      </ol>
      {confirmDialog}
    </Sheet>
  );
}
