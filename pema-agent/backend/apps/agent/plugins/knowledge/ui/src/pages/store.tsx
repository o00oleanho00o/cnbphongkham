/** "Kho tri thức": one page for the whole area, with its own tabs (the same in the clinic web and the dashboard). */
import { createContext, useContext, useMemo, useState } from "react";

import { Tabs } from "../parts";
import { GapsPage } from "./gaps";
import { ServicesPage } from "./services";
import { SettingsPage } from "./settings";
import { SourcesPage } from "./sources";
import { TryPage } from "./try";

export type StoreTab = "sources" | "services" | "try" | "gaps" | "settings";

const TABS = [
  { id: "sources", label: "Nguồn" },
  { id: "services", label: "Dịch vụ" },
  { id: "try", label: "Thử tìm" },
  { id: "gaps", label: "Câu hỏi chưa có tài liệu" },
  { id: "settings", label: "Cài đặt" },
] as const;

interface Focus {
  /** Open the detail of this source when the sources tab shows. */
  source?: string;
}

interface StoreNav {
  /** Goes to another tab; `focus.source` opens that source's detail. */
  go: (tab: StoreTab, focus?: Focus) => void;
  /** Read by the sources tab once; empty after. */
  focus: Focus;
  clearFocus: () => void;
}

const NavContext = createContext<StoreNav | null>(null);

export function useStoreNav(): StoreNav {
  const value = useContext(NavContext);
  if (!value) throw new Error("useStoreNav must be used inside the knowledge store page");
  return value;
}

export function StorePage() {
  const [tab, setTab] = useState<StoreTab>("sources");
  const [focus, setFocus] = useState<Focus>({});
  const nav = useMemo<StoreNav>(
    () => ({
      go: (next, nextFocus = {}) => {
        setFocus(nextFocus);
        setTab(next);
      },
      focus,
      clearFocus: () => setFocus({}),
    }),
    [focus],
  );
  return (
    <NavContext.Provider value={nav}>
      <Tabs label="Kho tri thức" items={TABS} value={tab} onChange={(next) => nav.go(next)} />
      {tab === "sources" && <SourcesPage />}
      {tab === "services" && <ServicesPage />}
      {tab === "try" && <TryPage />}
      {tab === "gaps" && <GapsPage />}
      {tab === "settings" && <SettingsPage />}
    </NavContext.Provider>
  );
}
