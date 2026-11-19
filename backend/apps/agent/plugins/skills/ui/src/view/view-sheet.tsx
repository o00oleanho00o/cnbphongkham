/** One item, read-only: its text as the file it is, its history; download it, switch it on or off, or ask the chat to edit it. */
import { useState } from "react";

import { messageOf, skills } from "../client";
import { KIND_LABEL, ORIGIN_LABEL, STATUS_LABEL, STATUS_TONE, formatTime, scopeLabel } from "../logic";
import { Chip, Sheet, Tabs } from "../parts";
import { ScopeEditor } from "../scope/scope-editor";
import { ui } from "../sdk";
import { downloadText, toSkillFile } from "../skill-file";
import type { Choices, Item, Saved, Status } from "../types";
import { History } from "./history";

const TABS = [
  { id: "text", label: "Nội dung" },
  { id: "scope", label: "Nơi áp dụng" },
  { id: "history", label: "Lịch sử" },
] as const;

type Tab = (typeof TABS)[number]["id"];

const STATUS_ACTIONS: Record<Status, readonly { to: Status; label: string; primary: boolean }[]> = {
  draft: [
    { to: "active", label: "Dùng", primary: true },
    { to: "archived", label: "Cất", primary: false },
  ],
  active: [{ to: "archived", label: "Tắt", primary: false }],
  archived: [{ to: "active", label: "Dùng lại", primary: true }],
};

export function ViewSheet({
  item,
  choices,
  onClose,
  onChanged,
  onEdit,
}: {
  item: Item;
  choices: Choices;
  onClose: () => void;
  onChanged: () => void;
  onEdit: (item: Item) => void;
}) {
  const [current, setCurrent] = useState(item);
  const [tab, setTab] = useState<Tab>("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const scopes = current.scopes.length === 0 ? ["agent"] : current.scopes;

  function take(saved: Saved) {
    setCurrent(saved.item);
    onChanged();
  }

  async function setStatus(status: Status) {
    setBusy(true);
    setError("");
    try {
      take(await skills.update(current.id, { status, reason: `đổi sang ${STATUS_LABEL[status].toLowerCase()}` }));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={current.name}
      onClose={onClose}
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <ui.Button variant="secondary" onClick={() => downloadText(`${current.name}.md`, toSkillFile(current))}>
            Tải về
          </ui.Button>
          {STATUS_ACTIONS[current.status].map((action) => (
            <ui.Button
              key={action.to}
              variant={action.primary ? "primary" : "secondary"}
              busy={busy}
              onClick={() => void setStatus(action.to)}
            >
              {action.label}
            </ui.Button>
          ))}
          <ui.Button onClick={() => onEdit(current)}>Sửa bằng chat</ui.Button>
        </div>
      }
    >
      <p className="flex flex-wrap items-center gap-2">
        <ui.Badge>{KIND_LABEL[current.kind]}</ui.Badge>
        <ui.Badge tone={STATUS_TONE[current.status]}>{STATUS_LABEL[current.status]}</ui.Badge>
        <span className="text-label text-ink-soft">
          Phiên bản {current.version} · {ORIGIN_LABEL[current.origin]} · {current.updated_by} ·{" "}
          {formatTime(current.updated_at)}
        </span>
      </p>
      <p className="text-body text-ink">{current.description}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-label text-ink-soft">Áp dụng:</span>
        {scopes.map((scope) => (
          <Chip key={scope}>{scopeLabel(scope)}</Chip>
        ))}
      </div>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <Tabs label="Chi tiết" items={TABS} value={tab} onChange={setTab} />
      {tab === "text" && (
        <pre className="overflow-auto rounded-tile border border-line bg-tile p-3 text-small whitespace-pre-wrap text-ink">
          {toSkillFile(current)}
        </pre>
      )}
      {tab === "scope" && (
        <ScopeEditor
          key={current.version}
          item={current}
          choices={choices}
          onSaved={(saved) => take({ item: saved, warnings: [] })}
        />
      )}
      {tab === "history" && <History itemId={current.id} onRestored={take} />}
    </Sheet>
  );
}
