/** "Cuộc trò chuyện": what the channels kept, newest first; search, filter by channel, open one. */
import { useCallback, useEffect, useState } from "react";

import { conversations, messageOf } from "../client";
import { formatTime, titleOf } from "../logic";
import { ui } from "../sdk";
import type { Conversation } from "../types";
import { ChatSheet } from "./chat-sheet";

const PAGE = 30;

function Row({ conversation, onOpen }: { conversation: Conversation; onOpen: () => void }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-2 rounded-tile border border-line bg-surface p-4">
      <div className="min-w-0 space-y-1">
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

  const load = useCallback(async () => {
    setError("");
    try {
      const found = await conversations.list({ channel, q: search, limit: PAGE, offset: 0 });
      setRows(found.conversations);
      setTotal(found.total);
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
      <ul className="space-y-2">
        {(rows ?? []).map((conversation) => (
          <Row key={conversation.id} conversation={conversation} onOpen={() => setOpen(conversation)} />
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
