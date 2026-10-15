/** One conversation as it went: the customer on the left, staff and the agent on the right, with who wrote each. */
import { useCallback, useEffect, useState } from "react";

import { conversations, messageOf } from "../client";
import { ROLE_LABEL, ROLE_TONE, formatTime, titleOf } from "../logic";
import { Sheet } from "../parts";
import { ui } from "../sdk";
import type { Conversation, Message, Role } from "../types";

const BUBBLE: Record<Role, string> = {
  customer: "bg-tile text-heading",
  staff: "bg-brand-500/10 text-heading",
  agent: "border border-line bg-surface text-ink",
};
const SIDE: Record<Role, string> = { customer: "justify-start", staff: "justify-end", agent: "justify-end" };

function Bubble({ message }: { message: Message }) {
  const who = message.sender_name || ROLE_LABEL[message.role];
  return (
    <div className={`flex ${SIDE[message.role]}`}>
      <div className={`max-w-[85%] space-y-1 rounded-tile px-3.5 py-2.5 ${BUBBLE[message.role]}`}>
        <p className="flex flex-wrap items-center gap-2 text-label text-ink-soft">
          <span className="font-bold">{who}</span>
          <ui.Badge tone={ROLE_TONE[message.role]}>{ROLE_LABEL[message.role]}</ui.Badge>
          <span>{formatTime(message.at)}</span>
        </p>
        <p className="text-body whitespace-pre-wrap">{message.text}</p>
      </div>
    </div>
  );
}

export function ChatSheet({
  conversation,
  onClose,
  onChanged,
}: {
  conversation: Conversation;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [current, setCurrent] = useState(conversation);
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const opened = await conversations.open(conversation.id);
      setCurrent(opened.conversation);
      setMessages(opened.messages);
    } catch (err) {
      setError(messageOf(err));
      setMessages([]);
    }
  }, [conversation.id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function leaveOut(excluded: boolean) {
    setBusy(true);
    setError("");
    try {
      setCurrent(await conversations.leaveOut(current.id, excluded));
      onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    setError("");
    try {
      await conversations.remove(current.id);
      onChanged();
      onClose();
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={titleOf(current)}
      onClose={onClose}
      footer={
        asking ? (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="text-small text-ink-soft">
              Xóa cả cuộc trò chuyện này và các kịch bản rút ra từ nó?
            </span>
            <ui.Button variant="danger" busy={busy} onClick={() => void remove()}>
              Xóa
            </ui.Button>
            <ui.Button variant="ghost" onClick={() => setAsking(false)}>
              Hủy
            </ui.Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-end gap-2">
            <ui.Button variant="secondary" busy={busy} onClick={() => void leaveOut(!current.excluded)}>
              {current.excluded ? "Lưu lại cuộc này" : "Không lưu cuộc này nữa"}
            </ui.Button>
            <ui.Button variant="danger" disabled={busy} onClick={() => setAsking(true)}>
              Xóa cuộc trò chuyện
            </ui.Button>
          </div>
        )
      }
    >
      <p className="flex flex-wrap items-center gap-2">
        <ui.Badge>{current.is_group ? "Nhóm" : "Trực tiếp"}</ui.Badge>
        <ui.Badge tone="info">{current.channel}</ui.Badge>
        {current.excluded && <ui.Badge tone="warning">Không lưu tin mới</ui.Badge>}
        <span className="text-label text-ink-soft">
          {current.message_count} tin · {formatTime(current.first_at)} đến {formatTime(current.last_at)}
        </span>
      </p>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {messages === null && <ui.Empty>Đang tải…</ui.Empty>}
      {messages !== null && messages.length === 0 && !error && <ui.Empty>Chưa có tin nào.</ui.Empty>}
      <div className="space-y-3">
        {(messages ?? []).map((message) => (
          <Bubble key={message.seq} message={message} />
        ))}
      </div>
    </Sheet>
  );
}
