/** "Kỹ năng": one page for the whole area, with its own tabs (the same in the clinic web and the dashboard). */
import { useEffect, useState } from "react";

import { choices as readChoices } from "../client";
import { type Prefill, ChatPage } from "../chat/chat-page";
import { Tabs } from "../parts";
import type { Choices, Item } from "../types";
import { EffectivePage } from "./effective";
import { ListPage } from "./list";

const TABS = [
  { id: "chat", label: "Soạn bằng chat" },
  { id: "list", label: "Danh sách" },
  { id: "effective", label: "Kênh nhận gì" },
] as const;

type Tab = (typeof TABS)[number]["id"];

const NO_CHOICES: Choices = { channels: [], plugins: [] };

export function SkillsPage() {
  const [tab, setTab] = useState<Tab>("chat");
  const [choices, setChoices] = useState<Choices>(NO_CHOICES);
  const [prefill, setPrefill] = useState<Prefill | null>(null);

  useEffect(() => {
    void readChoices().then(setChoices);
  }, []);

  function editWithChat(item: Item) {
    setPrefill((before) => ({ text: `Sửa kỹ năng "${item.name}": `, nonce: (before?.nonce ?? 0) + 1 }));
    setTab("chat");
  }

  return (
    <>
      <Tabs label="Kỹ năng" items={TABS} value={tab} onChange={setTab} />
      <div hidden={tab !== "chat"}>
        <ChatPage choices={choices} prefill={prefill} />
      </div>
      {tab === "list" && <ListPage onEdit={editWithChat} onWrite={() => setTab("chat")} />}
      {tab === "effective" && <EffectivePage choices={choices} />}
    </>
  );
}
