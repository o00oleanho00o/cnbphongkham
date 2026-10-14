/** "Soạn bằng chat": staff talk to the assistant, which writes the skill; a file can also be added straight in. */
import { type DragEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { type Entry, AddFiles, readFiles } from "../add/add-files";
import { ui } from "../sdk";
import type { Choices } from "../types";
import { type ChatItem, DraftCard } from "./draft-card";
import { type ChatMessage, useChat } from "./use-chat";

const SUGGESTIONS = [
  "Soạn kỹ năng trả lời khi khách hỏi giá và đặt lịch khám",
  "Viết quy tắc giọng điệu: xưng em, gọi khách là anh/chị, nhẹ nhàng",
  "Tôi dán đoạn tin nhắn mẫu của phòng khám, bạn rút thành một kỹ năng",
];

/** A change that asks the chat to open with this text (from "Sửa bằng chat" in the list). */
export interface Prefill {
  text: string;
  nonce: number;
}

function Bubble({ message, onItem }: { message: ChatMessage; onItem: (next: ChatItem) => void }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-tile bg-tile px-3.5 py-2.5 text-body whitespace-pre-wrap text-heading">
          {message.text}
        </p>
      </div>
    );
  }
  if (message.role === "error") return <ui.Notice tone="danger">{message.text}</ui.Notice>;
  return (
    <div className="max-w-[92%] space-y-3">
      <p className="text-body whitespace-pre-wrap text-ink">{message.text}</p>
      {message.items.map((entry) => (
        <DraftCard key={entry.item.id} entry={entry} onChange={onItem} />
      ))}
    </div>
  );
}

function hasFiles(event: DragEvent): boolean {
  return Array.from(event.dataTransfer.types).includes("Files");
}

export function ChatPage({ choices, prefill }: { choices: Choices; prefill: Prefill | null }) {
  const chat = useChat(choices);
  const [draft, setDraft] = useState("");
  const [entries, setEntries] = useState<Entry[] | null>(null);
  const [dragging, setDragging] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [chat.messages.length, chat.busy]);

  useEffect(() => {
    if (prefill === null) return;
    setDraft(prefill.text);
    field.current?.focus();
  }, [prefill]);

  function submit() {
    const text = draft;
    setDraft("");
    void chat.send(text);
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    submit();
  }

  async function takeFiles(files: readonly File[]) {
    if (files.length === 0) return;
    setEntries(await readFiles(files));
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    void takeFiles(Array.from(event.dataTransfer.files));
  }

  const empty = chat.messages.length === 0;

  return (
    <div
      className="relative flex min-h-[32rem] flex-col rounded-tile border border-line bg-surface"
      style={{ height: "calc(100vh - 14rem)" }}
      onDragOver={(event) => {
        if (!hasFiles(event)) return;
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(event) => {
        const next = event.relatedTarget;
        if (next instanceof Node && event.currentTarget.contains(next)) return; // moving between children
        setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <p className="text-small text-ink-soft">Nói với trợ lý điều bạn muốn agent làm, trợ lý soạn thành kỹ năng.</p>
        <ui.Button variant="ghost" disabled={empty || chat.busy} onClick={chat.restart}>
          Cuộc trò chuyện mới
        </ui.Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {entries !== null && (
          <AddFiles entries={entries} onClose={() => setEntries(null)} onAdded={() => undefined} />
        )}
        {empty && entries === null && (
          <div className="space-y-3 py-6 text-center">
            <p className="text-body font-bold text-heading">Bạn muốn agent biết làm gì?</p>
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <ui.Button key={suggestion} variant="secondary" onClick={() => void chat.send(suggestion)}>
                  {suggestion}
                </ui.Button>
              ))}
            </div>
          </div>
        )}
        {chat.messages.map((message) => (
          <Bubble key={message.id} message={message} onItem={(next) => chat.updateItem(message.id, next)} />
        ))}
        {chat.busy && <p className="text-small text-ink-soft">Trợ lý đang soạn…</p>}
        <div ref={bottom} />
      </div>

      <div className="space-y-2 border-t border-line p-3">
        <textarea
          ref={field}
          aria-label="Tin nhắn cho trợ lý"
          rows={3}
          value={draft}
          placeholder="Nhập tin nhắn. Enter để gửi, Shift+Enter xuống dòng."
          className={`${ui.FIELD_CLASS} min-h-20 resize-y`}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKey}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <input
            ref={picker}
            type="file"
            multiple
            accept=".md,.markdown,.txt"
            className="hidden"
            onChange={(event) => {
              void takeFiles(Array.from(event.target.files ?? []));
              event.target.value = "";
            }}
          />
          <ui.Button variant="secondary" onClick={() => picker.current?.click()}>
            Thêm file kỹ năng
          </ui.Button>
          <ui.Button busy={chat.busy} disabled={draft.trim() === ""} onClick={submit}>
            Gửi
          </ui.Button>
        </div>
      </div>

      {dragging && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-tile border-2 border-dashed border-link bg-surface/90">
          <p className="text-body font-bold text-link">Thả file .md vào đây để thêm làm kỹ năng</p>
        </div>
      )}
    </div>
  );
}
