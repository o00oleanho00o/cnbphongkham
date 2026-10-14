/** "Hội thoại": one page for the whole area, with its own tabs (the same in the clinic web and the dashboard). */
import { useEffect, useState } from "react";

import { channelNames } from "../client";
import { Tabs } from "../parts";
import { ListPage } from "./list";
import { ScenariosPage } from "./scenarios";
import { SettingsPage } from "./settings";

const TABS = [
  { id: "list", label: "Cuộc trò chuyện" },
  { id: "scenarios", label: "Kịch bản" },
  { id: "settings", label: "Cài đặt" },
] as const;

type Tab = (typeof TABS)[number]["id"];

export function ConversationsPage() {
  const [tab, setTab] = useState<Tab>("list");
  const [channels, setChannels] = useState<string[]>([]);

  useEffect(() => {
    void channelNames().then(setChannels);
  }, []);

  return (
    <>
      <Tabs label="Hội thoại" items={TABS} value={tab} onChange={setTab} />
      {tab === "list" && <ListPage channels={channels} />}
      {tab === "scenarios" && <ScenariosPage channels={channels} />}
      {tab === "settings" && <SettingsPage channels={channels} />}
    </>
  );
}
