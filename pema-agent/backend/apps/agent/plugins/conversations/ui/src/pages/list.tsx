/** "Cuộc trò chuyện": what the channels kept, newest first; search, filter by channel, open one, delete the ticked. */
import { useCallback, useEffect, useState } from "react";

import { conversations, messageOf } from "../client";
import { formatTime, MAX_DELETE, tickedAll, tickedOne, titleOf } from "../logic";
import { ui } from "../sdk";
import type { Conversation } from "../types";
import { ChatSheet } from "./chat-sheet";

const PAGE = 30;

interface RowProps {
  conversation: Conversation;
  checked: boolean;
  full: boolean;
  onToggle: () => void;
  onOpen: () => void;
}

function Row({ conversation, checked, full, onToggle, onOpen }: RowProps) {
  return (
    <li className="flex flex-wrap items-start gap-3 rounded-tile border border-line bg-surface p-4">
      <input
        type="checkbox"
        className="mt-1 size-4"
        aria-label={`Chọn ${titleOf(conversation)}`}
        checked={checked}
        disabled={full && !checked}
        onChange={onToggle}
      />
      <div className="min-w-0 flex-1 space-y-1">
        <p className="flex flex-wrap items-center gap-2">
          <span className="text-body font-bold break-all text-heading">{titleOf(conversation)}</span>
          <ui.Badge>{conversation.is_group ? "Nhóm" : "Trực tiếp"}</ui.Badge>
          <ui.Badge tone="info">{conversation.channel}</ui.Badge>
          {conversation.excluded && <ui.Badge tone="warning">Không lưu tin mới</ui.Badge>}
        </p>
        <p className="text-label text-ink-soft">
          {conversation.message_count} tin · mới nhất {formatTime(conversation.last_at)}
        </p>
      </div>
      <ui.Button variant="secondary" onClick={onOpen}>
        Xem
      </ui.Button>
    </li>
  );
}

export function ListPage({ channels }: { channels: readonly string[] }) {
  const [rows, setRows] = useState<Conversation[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState("");
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Conversation | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [asking, setAsking] = useState(false);
  const [removing, setRemoving] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const found = await conversations.list({ channel, q: search, limit: PAGE, offset: 0 });
      setRows(found.conversations);
      setTotal(found.total);
      setSelected([]);
      setAsking(false);
    } catch (err) {
      setError(messageOf(err));
      setRows([]);
    }
  }, [channel, search]);

  useEffect(() => {
    void load();
  }, [load]);

  async function more() {
    setLoadingMore(true);
    try {
      const found = await conversations.list({ channel, q: search, limit: PAGE, offset: rows?.length ?? 0 });
      setRows((before) => [...(before ?? []), ...found.conversations]);
      setTotal(found.total);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setLoadingMore(false);
    }
  }

  async function removeSelected() {
    setRemoving(true);
    setError("");
    try {
      await conversations.removeMany(selected);
      await load();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setRemoving(false);
      setAsking(false);
    }
  }

  const shownIds = (rows ?? []).map((conversation) => conversation.id);
  const options = [{ value: "", label: "Mọi kênh" }, ...channels.map((name) => ({ value: name, label: name }))];

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Cuộc trò chuyện đã lưu"
        subtitle="Cả hai bên, khách và nhân viên, cùng câu trả lời của trợ lý. Chỉ những kênh được bật ở tab Cài đặt mới lưu."
      />
      <form
        className="flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSearch(typed.trim());
        }}
      >
        <div className="min-w-48 flex-1">
          <ui.Input
            aria-label="Tìm trong tên và tin nhắn"
            placeholder="Tìm trong tên và tin nhắn"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
        </div>
        <ui.Select
          aria-label="Lọc theo kênh"
          value={channel}
          options={options}
          onChange={(event) => setChannel(event.target.value)}
        />
        <ui.Button type="submit" variant="secondary">
          Tìm
        </ui.Button>
      </form>
      {error && (
        <ui.Notice tone="danger">
          <span className="flex flex-wrap items-center justify-between gap-2">
            {error}
            <ui.Button variant="secondary" onClick={() => void load()}>
              Thử lại
            </ui.Button>
          </span>
        </ui.Notice>
      )}
      {rows === null && <p className="py-6 text-center text-small text-ink-soft">Đang tải…</p>}
      {rows !== null && rows.length === 0 && !error && (
        <ui.Card>
          <p className="text-center text-body font-bold text-heading">Chưa có cuộc trò chuyện nào</p>
          <ui.Empty>Bật một kênh ở tab Cài đặt để bắt đầu lưu. Mặc định mọi kênh đều tắt.</ui.Empty>
        </ui.Card>
      )}
      {shownIds.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex min-h-11 items-center gap-2 text-small text-ink">
            <input
              type="checkbox"
              className="size-4"
              checked={selected.length > 0 && selected.length === Math.min(shownIds.length, MAX_DELETE)}
              onChange={() => setSelected(tickedAll(selected, shownIds))}
            />
            {shownIds.length > MAX_DELETE ? `Chọn ${MAX_DELETE} cuộc đầu` : "Chọn tất cả đang hiện"}
          </label>
          {asking ? (
            <div className="flex flex-wrap items-center justify-end gap-2">
              <span className="text-small text-ink-soft">
                {`Xóa ${selected.length} cuộc trò chuyện và các kịch bản rút ra từ chúng? Không hoàn tác được.`}
              </span>
              <ui.Button variant="danger" busy={removing} onClick={() => void removeSelected()}>
                Xóa
              </ui.Button>
              <ui.Button variant="ghost" onClick={() => setAsking(false)}>
                Hủy
              </ui.Button>
            </div>
          ) : (
            <ui.Button variant="danger" disabled={selected.length === 0} onClick={() => setAsking(true)}>
              {selected.length === 0 ? "Xóa các cuộc đã chọn" : `Xóa ${selected.length} cuộc đã chọn`}
            </ui.Button>
          )}
        </div>
      )}
      <ul className="space-y-2">
        {(rows ?? []).map((conversation) => (
          <Row
            key={conversation.id}
            conversation={conversation}
            checked={selected.includes(conversation.id)}
            full={selected.length >= MAX_DELETE}
            onToggle={() => setSelected((now) => tickedOne(now, conversation.id))}
            onOpen={() => setOpen(conversation)}
          />
        ))}
      </ul>
      {rows !== null && rows.length < total && (
        <div className="flex justify-center">
          <ui.Button variant="secondary" busy={loadingMore} onClick={() => void more()}>
            {`Xem thêm (${total - rows.length})`}
          </ui.Button>
        </div>
      )}
      {open !== null && (
        <ChatSheet key={open.id} conversation={open} onClose={() => setOpen(null)} onChanged={() => void load()} />
      )}
    </div>
  );
}
