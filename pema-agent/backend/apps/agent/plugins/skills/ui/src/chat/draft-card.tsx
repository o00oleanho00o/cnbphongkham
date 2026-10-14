/** An item the assistant saved, shown in the chat: read it, press "Dùng" to let the agent use it, put it aside, or
 * undo a change it made to an item already in use. */
import { useState } from "react";

import { messageOf, skills } from "../client";
import { KIND_LABEL, STATUS_LABEL, STATUS_TONE, scopesSummary } from "../logic";
import { Chip } from "../parts";
import { ui } from "../sdk";
import { toSkillFile } from "../skill-file";
import type { Item, Status } from "../types";

export interface ChatItem {
  item: Item;
  /** The version before the assistant changed it; none when it made the item. */
  beforeVersion: number | null;
}

export function DraftCard({ entry, onChange }: { entry: ChatItem; onChange: (next: ChatItem) => void }) {
  const { item, beforeVersion } = entry;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scopes = item.scopes.length === 0 ? ["agent"] : item.scopes;

  async function run(work: () => Promise<Item>) {
    setBusy(true);
    setError("");
    try {
      onChange({ item: await work(), beforeVersion: null });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  const setStatus = (status: Status, reason: string) =>
    run(async () => (await skills.update(item.id, { status, reason })).item);
  const undo = () =>
    run(async () => {
      if (beforeVersion === null) return item;
      return (await skills.restore(item.id, beforeVersion)).item;
    });

  return (
    <div className="space-y-2 rounded-tile border border-line bg-surface p-3">
      <p className="flex flex-wrap items-center gap-2">
        <span className="text-body font-bold break-all text-heading">{item.name}</span>
        <ui.Badge>{KIND_LABEL[item.kind]}</ui.Badge>
        <ui.Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</ui.Badge>
        <span className="text-label text-ink-soft">phiên bản {item.version}</span>
      </p>
      <p className="text-body text-ink">{item.description}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-label text-ink-soft">Áp dụng:</span>
        {scopes.map((scope) => (
          <Chip key={scope}>{scopesSummary([scope === "agent" ? "agent" : scope])}</Chip>
        ))}
      </div>
      <details>
        <summary className="cursor-pointer text-small text-link">Xem nội dung</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded-tile border border-line bg-tile p-3 text-small whitespace-pre-wrap text-ink">
          {toSkillFile(item)}
        </pre>
      </details>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <div className="flex flex-wrap items-center gap-2">
        {item.status === "draft" && (
          <ui.Button busy={busy} onClick={() => void setStatus("active", "bấm Dùng")}>
            Dùng
          </ui.Button>
        )}
        {item.status === "draft" && (
          <ui.Button variant="secondary" disabled={busy} onClick={() => void setStatus("archived", "bỏ bản nháp")}>
            Bỏ
          </ui.Button>
        )}
        {beforeVersion !== null && (
          <ui.Button variant="secondary" busy={busy} onClick={() => void undo()}>
            Hoàn tác
          </ui.Button>
        )}
      </div>
    </div>
  );
}
