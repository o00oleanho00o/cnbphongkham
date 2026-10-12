/** The detail of one source: header with its actions, and three tabs (structure, chunks, history). */
import { useEffect, useState } from "react";

import { ChunksTab } from "../detail/chunks-tab";
import { SourceHeader } from "../detail/header";
import { HistoryTab } from "../detail/history-tab";
import { StructureTab } from "../detail/structure-tab";
import { contentKey, useSource } from "../detail/use-source";
import { ConfirmDialog, Tabs } from "../parts";
import { ui } from "../sdk";
import type { Source } from "../types";

type DetailTab = "structure" | "chunks" | "history";

const TABS = [
  { id: "structure", label: "Bản dựng cấu trúc" },
  { id: "chunks", label: "Đoạn" },
  { id: "history", label: "Lịch sử" },
] as const;

export function SourceDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const { state, reload, replace } = useSource(id);
  const [tab, setTab] = useState<DetailTab>("structure");
  const [edited, setEdited] = useState<string | null>(null);
  const [leaving, setLeaving] = useState(false);
  const [notice, setNotice] = useState("");
  const unsaved = edited !== null;

  // The browser's own question when the page is closed or reloaded with text typed and not saved.
  useEffect(() => {
    if (!unsaved) return;
    const listener = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", listener);
    return () => window.removeEventListener("beforeunload", listener);
  }, [unsaved]);

  const goBack = () => (unsaved ? setLeaving(true) : onBack());

  if (state.kind === "loading") return <ui.Empty>Đang tải nguồn...</ui.Empty>;
  if (state.kind === "missing") {
    return (
      <div className="space-y-3">
        <ui.Notice tone="warning">Nguồn này không còn nữa.</ui.Notice>
        <ui.Button variant="secondary" onClick={onBack}>
          Về danh sách
        </ui.Button>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="space-y-3">
        <ui.Notice tone="danger">{state.message}</ui.Notice>
        <div className="flex gap-2">
          <ui.Button variant="secondary" onClick={onBack}>
            Về danh sách
          </ui.Button>
          <ui.Button onClick={reload}>Thử lại</ui.Button>
        </div>
      </div>
    );
  }

  const { source } = state;
  const key = contentKey(source);
  const changed = (next: Source) => replace(next);

  return (
    <div>
      <SourceHeader source={source} onChanged={changed} onBack={goBack} onDeleted={onBack} />
      {notice && <div className="mb-4"><ui.Notice tone="success">{notice}</ui.Notice></div>}
      <Tabs
        label="Chi tiết nguồn"
        items={TABS.map((item) => (item.id === "structure" && unsaved ? { ...item, label: `${item.label} (chưa lưu)` } : item))}
        value={tab}
        onChange={setTab}
      />
      {tab === "structure" && (
        <StructureTab
          source={source}
          contentKey={key}
          edited={edited}
          onEdit={setEdited}
          onSourceChanged={changed}
          onSplit={(created) => {
            setNotice(`Đã tách sang nguồn mới "${created.title}". Mở danh sách để xem lại.`);
            reload();
          }}
        />
      )}
      {tab === "chunks" && <ChunksTab sourceId={source.id} contentKey={key} />}
      {tab === "history" && <HistoryTab sourceId={source.id} contentKey={key} onRestored={changed} />}
      {leaving && (
        <ConfirmDialog
          title="Bỏ các sửa đổi chưa lưu?"
          onClose={() => setLeaving(false)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setLeaving(false)}>
                Ở lại
              </ui.Button>
              <ui.Button variant="danger" onClick={onBack}>
                Bỏ và rời đi
              </ui.Button>
            </>
          }
        >
          Bản dựng bạn đã sửa chưa được nạp lại. Rời đi sẽ mất phần đã sửa.
        </ConfirmDialog>
      )}
    </div>
  );
}
