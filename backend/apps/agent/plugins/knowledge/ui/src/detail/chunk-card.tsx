/** One chunk: where it sits, its text (plain, collapsible), its size and vector, and its two labels. */
import { useState } from "react";

import { knowledge } from "../client";
import { Chip } from "../parts";
import { ui } from "../sdk";
import type { Chunk, Service } from "../types";
import {
  KIND_OPTIONS,
  collapsedText,
  isInternalChunk,
  isLong,
  kindLabel,
  sizeWarning,
  toggled,
} from "./detail-logic";
import { useAction } from "./use-action";

export function ChunkCard({
  chunk,
  catalog,
  onChanged,
}: {
  chunk: Chunk;
  catalog: readonly Service[];
  onChanged: (chunk: Chunk) => void;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [services, setServices] = useState<readonly string[]>(chunk.services);
  const [kind, setKind] = useState(chunk.kind);
  const { busy, error, run } = useAction();
  const warning = sizeWarning(chunk.chars);
  const internal = isInternalChunk(chunk);

  function startEditing() {
    setServices(chunk.services);
    setKind(chunk.kind);
    setEditing(true);
  }

  async function save() {
    const saved = await run("save", () => knowledge.updateChunk(chunk.id, { services: [...services], kind }));
    if (!saved) return;
    onChanged({ ...chunk, services: [...services], kind });
    setEditing(false);
  }

  return (
    <article
      className={`space-y-2 rounded-tile border p-4 ${internal ? "border-warning-line bg-warning-soft" : "border-line bg-surface"}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 text-small font-semibold break-words text-heading">
          <span className="text-ink-soft">#{chunk.ordinal + 1} </span>
          {chunk.path}
        </p>
        <div className="flex flex-wrap items-center gap-1.5">
          {internal && <ui.Badge tone="warning">Kịch bản nội bộ</ui.Badge>}
          <ui.Badge tone={chunk.embedded ? "success" : "neutral"}>{chunk.embedded ? "Có vector" : "Chưa có vector"}</ui.Badge>
          <span className="text-label text-ink-soft">{chunk.chars} ký tự</span>
        </div>
      </div>
      <p className="text-small break-words whitespace-pre-wrap text-ink">{open ? chunk.text : collapsedText(chunk.text)}</p>
      {isLong(chunk.text) && (
        <button type="button" onClick={() => setOpen(!open)} className="text-small text-link">
          {open ? "Thu gọn" : "Xem đủ"}
        </button>
      )}
      {warning && <ui.Notice tone="warning">{warning}</ui.Notice>}
      {editing ? (
        <div className="space-y-3 rounded-tile border border-line bg-surface p-3">
          <fieldset>
            <legend className="mb-1.5 text-label font-semibold text-ink-soft">Dịch vụ</legend>
            <div className="flex flex-wrap gap-2">
              {catalog.map((service) => (
                <label
                  key={service.code}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line px-3 text-small sm:min-h-0 sm:py-1"
                >
                  <input
                    type="checkbox"
                    checked={services.includes(service.code)}
                    onChange={() => setServices(toggled(services, service.code))}
                  />
                  {service.name}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="sm:w-60">
            <ui.Field label="Loại">
              <ui.Select value={kind} options={KIND_OPTIONS} onChange={(event) => setKind(event.target.value)} />
            </ui.Field>
          </div>
          {error && <ui.Notice tone="danger">{error}</ui.Notice>}
          <div className="flex flex-wrap justify-end gap-2">
            <ui.Button variant="secondary" onClick={() => setEditing(false)}>
              Hủy
            </ui.Button>
            <ui.Button busy={busy === "save"} onClick={save}>
              Lưu nhãn
            </ui.Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <Chip>{kindLabel(chunk.kind)}</Chip>
          {chunk.services.map((code) => (
            <Chip key={code}>{code}</Chip>
          ))}
          <ui.Button variant="ghost" onClick={startEditing}>
            Sửa nhãn
          </ui.Button>
        </div>
      )}
    </article>
  );
}
