/** "Kỹ năng": one page for the whole area, with its own tabs (the same in the clinic web and the dashboard). */
import { useEffect, useState } from "react";

import { choices as readChoices } from "../client";
import { Tabs } from "../parts";
import type { Choices } from "../types";
import { EffectivePage } from "./effective";
import { ListPage } from "./list";

const TABS = [
  { id: "list", label: "Danh sách" },
  { id: "effective", label: "Kênh nhận gì" },
] as const;

type Tab = (typeof TABS)[number]["id"];

const NO_CHOICES: Choices = { channels: [], plugins: [] };

export function SkillsPage() {
  const [tab, setTab] = useState<Tab>("list");
  const [choices, setChoices] = useState<Choices>(NO_CHOICES);

  useEffect(() => {
    void readChoices().then(setChoices);
  }, []);

  return (
    <>
      <Tabs label="Kỹ năng" items={TABS} value={tab} onChange={setTab} />
      {tab === "list" && <ListPage choices={choices} />}
      {tab === "effective" && <EffectivePage choices={choices} />}
    </>
  );
}
