/** The state of the chat with the assistant that writes items: the transcript, sending a turn, starting over. */
import { useCallback, useState } from "react";

import { messageOf, skills } from "../client";
import type { Choices } from "../types";
import type { ChatItem } from "./draft-card";

export type ChatMessage =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; items: ChatItem[] }
  | { id: number; role: "error"; text: string };

function newConversation(): string {
  return crypto.randomUUID();
}

export function useChat(known: Choices) {
  const [conversation, setConversation] = useState(newConversation);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);

  const append = useCallback(
    (message: (id: number) => ChatMessage) => setMessages((before) => [...before, message(before.length)]),
    [],
  );

  const send = useCallback(
    async (text: string) => {
      const said = text.trim();
      if (said === "" || busy) return;
      append((id) => ({ id, role: "user", text: said }));
      setBusy(true);
      try {
        const answer = await skills.chat(conversation, said, known);
        const items = answer.items.map(({ item, before_version }) => ({ item, beforeVersion: before_version }));
        append((id) => ({ id, role: "assistant", text: answer.reply, items }));
      } catch (err) {
        append((id) => ({ id, role: "error", text: messageOf(err) }));
      } finally {
        setBusy(false);
      }
    },
    [append, busy, conversation, known],
  );

  /** Replaces one saved item inside the transcript (after "Dùng", "Bỏ" or "Hoàn tác"). */
  const updateItem = useCallback((messageId: number, next: ChatItem) => {
    setMessages((before) =>
      before.map((message) =>
        message.id === messageId && message.role === "assistant"
          ? { ...message, items: message.items.map((entry) => (entry.item.id === next.item.id ? next : entry)) }
          : message,
      ),
    );
  }, []);

  const restart = useCallback(() => {
    setConversation(newConversation());
    setMessages([]);
  }, []);

  return { messages, busy, send, updateItem, restart };
}
