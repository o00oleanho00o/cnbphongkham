/** One item in a sheet: write it (kind, name, where it applies, the text) and, for an existing one, its history. */
import { useState } from "react";

import { messageOf, skills } from "../client";
import {
  type Draft,
  KINDS,
  MAX_DESCRIPTION,
  STATUSES,
  bodyLimit,
  draftOf,
  emptyDraft,
  isChanged,
  problems,
} from "../logic";
import { Sheet, Tabs } from "../parts";
import { ui } from "../sdk";
import type { Choices, Item, Kind, Saved, Status } from "../types";
import { History } from "./history";
import { ScopePicker } from "./scope-picker";

const TABS = [
  { id: "text", label: "Nội dung" },
  { id: "history", label: "Lịch sử" },
] as const;

type Tab = (typeof TABS)[number]["id"];

function isKind(value: string): value is Kind {
  return KINDS.some((kind) => kind.id === value);
}

function isStatus(value: string): value is Status {
  return STATUSES.some((status) => status.id === value);
}

export function ItemSheet({
  item,
  choices,
  onClose,
  onSaved,
}: {
  /** The item being changed; none to write a new one. */
  item: Item | null;
  choices: Choices;
  onClose: () => void;
  /** Called after every save and restore, so the list reads again. */
  onSaved: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(item ? draftOf(item) : emptyDraft());
  const [tab, setTab] = useState<Tab>("text");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [shown, setShown] = useState(false);
  const [current, setCurrent] = useState<Item | null>(item);

  const found = problems(draft);
  const hint = KINDS.find((kind) => kind.id === draft.kind)?.hint ?? "";
  const limit = bodyLimit(draft.kind);
  const changed = isChanged(current, draft);
  const set = (patch: Partial<Draft>) => setDraft((before) => ({ ...before, ...patch }));

  function saved(result: Saved) {
    setCurrent(result.item);
    setDraft(draftOf(result.item));
    setWarnings(result.warnings);
    onSaved();
    if (result.warnings.length === 0) onClose();
  }

  async function save() {
    setShown(true);
    if (found.length > 0) return;
    setBusy(true);
    setError("");
    try {
      saved(await write());
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function write(): Promise<Saved> {
    const { kind, name, description, body, status, scopes, reason } = draft;
    if (current === null) return skills.create({ kind, name, description, body, status, scopes });
    return skills.update(current.id, { name, description, body, status, scopes, reason });
  }

  const footer = (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <ui.Button variant="secondary" onClick={onClose}>
        Đóng
      </ui.Button>
      <ui.Button busy={busy} disabled={!changed} onClick={() => void save()}>
        {current === null ? "Thêm" : "Lưu"}
      </ui.Button>
    </div>
  );

  return (
    <Sheet title={current ? current.name : "Thêm mới"} onClose={onClose} footer={tab === "text" ? footer : undefined}>
      {current && <Tabs label="Mục" items={TABS} value={tab} onChange={setTab} />}
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {warnings.length > 0 && (
        <ui.Notice tone="warning">
          <span className="block font-medium">Đã lưu. Lưu ý:</span>
          {warnings.map((warning) => (
            <span key={warning} className="block">
              {warning}
            </span>
          ))}
        </ui.Notice>
      )}
      {tab === "history" && current && (
        <History
          itemId={current.id}
          onRestored={(result) => {
            setCurrent(result.item);
            setDraft(draftOf(result.item));
            onSaved();
            setTab("text");
          }}
        />
      )}
      {tab === "text" && (
        <>
          <ui.Field label="Loại" hint={hint}>
            <ui.Select
              value={draft.kind}
              disabled={current !== null}
              options={KINDS.map((kind) => ({ value: kind.id, label: kind.label }))}
              onChange={(event) => {
                if (isKind(event.target.value)) set({ kind: event.target.value });
              }}
            />
          </ui.Field>
          <ui.Field label="Tên" hint="Chữ thường, số, dấu chấm, gạch dưới hoặc gạch ngang. Ví dụ: tra-loi-gia">
            <ui.Input value={draft.name} onChange={(event) => set({ name: event.target.value })} />
          </ui.Field>
          <ui.Field
            label="Mô tả một dòng"
            hint={`${draft.description.length}/${MAX_DESCRIPTION} · Với kỹ năng: khi nào dùng nó. Agent thấy dòng này trong mục lục.`}
          >
            <ui.Input value={draft.description} onChange={(event) => set({ description: event.target.value })} />
          </ui.Field>
          <ui.Field label="Áp dụng cho">
            <ScopePicker scopes={draft.scopes} choices={choices} onChange={(scopes) => set({ scopes })} />
          </ui.Field>
          <ui.Field label="Nội dung" hint={`${draft.body.length}/${limit} ký tự · Markdown`}>
            <textarea
              rows={14}
              value={draft.body}
              onChange={(event) => set({ body: event.target.value })}
              className={`${ui.FIELD_CLASS} font-mono text-small`}
            />
          </ui.Field>
          <ui.Field label="Trạng thái" hint="Chỉ mục đang dùng mới đến được agent.">
            <ui.Select
              value={draft.status}
              options={STATUSES.map((status) => ({ value: status.id, label: status.label }))}
              onChange={(event) => {
                if (isStatus(event.target.value)) set({ status: event.target.value });
              }}
            />
          </ui.Field>
          {current && (
            <ui.Field label="Lý do sửa (không bắt buộc)" hint="Hiện trong lịch sử.">
              <ui.Input value={draft.reason} onChange={(event) => set({ reason: event.target.value })} />
            </ui.Field>
          )}
          {shown && found.length > 0 && (
            <ui.Notice tone="danger">
              {found.map((problem) => (
                <span key={problem} className="block">
                  {problem}
                </span>
              ))}
            </ui.Notice>
          )}
        </>
      )}
    </Sheet>
  );
}
