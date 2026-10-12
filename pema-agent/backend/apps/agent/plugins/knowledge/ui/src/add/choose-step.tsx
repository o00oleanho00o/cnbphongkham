/** Step 1 "Chọn cách thêm": three ways (files, typed text, a folder) and what each one needs. */
import { type DragEvent, type ReactNode, useRef, useState } from "react";

import { FILE_EXTENSIONS, MAX_FILE_BYTES, MAX_TEXT_CHARS, formatSize } from "../logic";
import { ui } from "../sdk";
import { type Way, MAX_FOLDER_FILES } from "./add-logic";
import type { AddFlow, FileWay } from "./use-add-flow";

const WAYS: readonly { id: Way; title: string; hint: string }[] = [
  { id: "files", title: "Tải tệp", hint: `${FILE_EXTENSIONS.join(" ")}, mỗi tệp tối đa ${formatSize(MAX_FILE_BYTES)}` },
  { id: "text", title: "Gõ hoặc dán văn bản", hint: "FAQ ngắn, chính sách; Markdown cũng được" },
  { id: "folder", title: "Nhập hàng loạt từ thư mục", hint: `Cả bộ tài liệu, tối đa ${MAX_FOLDER_FILES} tệp` },
];

function WayCard({ way, active, onPick }: { way: (typeof WAYS)[number]; active: boolean; onPick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onPick}
      className={`min-h-11 rounded-tile border p-3 text-left ${active ? "border-link bg-surface-soft" : "border-line bg-surface hover:bg-surface-soft"}`}
    >
      <span className="block text-body font-bold text-heading">{way.title}</span>
      <span className="mt-1 block text-label text-ink-soft">{way.hint}</span>
    </button>
  );
}

function Rejections({ items }: { items: { name: string; reason: string }[] }) {
  if (items.length === 0) return null;
  return (
    <ul role="alert" className="space-y-1">
      {items.map((item) => (
        <li key={`${item.name}-${item.reason}`} className="text-label text-danger">
          <span className="font-semibold">{item.name}</span>: {item.reason}
        </li>
      ))}
    </ul>
  );
}

function PickedList({ flow, way }: { flow: AddFlow; way: FileWay }) {
  const list = flow.picked[way];
  if (list.length === 0) return null;
  return (
    <ul className="divide-y divide-line rounded-tile border border-line">
      {list.map((item) => (
        <li key={item.key} className="flex items-center justify-between gap-3 px-3 py-2">
          <span className="min-w-0">
            <span className="block truncate text-small text-ink">{item.path || item.file.name}</span>
            <span className="block text-label text-ink-soft">{formatSize(item.file.size)}</span>
          </span>
          <ui.Button variant="ghost" onClick={() => flow.removePicked(way, item.key)} aria-label={`Bỏ ${item.file.name}`}>
            Bỏ
          </ui.Button>
        </li>
      ))}
    </ul>
  );
}

function filesOf(list: FileList | null): File[] {
  return list ? Array.from(list) : [];
}

/** Drag and drop plus a button, for single files; the folder way has the button only. */
function Picker({ flow, way, children }: { flow: AddFlow; way: FileWay; children: ReactNode }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const isFolder = way === "folder";
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setOver(false);
    if (!isFolder) flow.addFiles(way, filesOf(event.dataTransfer.files));
  };
  const attach = (element: HTMLInputElement | null) => {
    input.current = element;
    if (isFolder) element?.setAttribute("webkitdirectory", "");
  };
  return (
    <div className="space-y-3">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          if (!isFolder) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-2 rounded-tile border border-dashed p-5 text-center ${over ? "border-link bg-surface-soft" : "border-line-strong"}`}
      >
        <p className="text-body text-ink-soft">{children}</p>
        <ui.Button variant="secondary" onClick={() => input.current?.click()}>
          {isFolder ? "Chọn thư mục" : "Chọn tệp"}
        </ui.Button>
        <input
          ref={attach}
          type="file"
          multiple
          className="sr-only"
          tabIndex={-1}
          aria-label={isFolder ? "Chọn thư mục" : "Chọn tệp"}
          accept={isFolder ? undefined : FILE_EXTENSIONS.join(",")}
          onChange={(event) => {
            flow.addFiles(way, filesOf(event.target.files));
            event.target.value = "";
          }}
        />
      </div>
      {flow.notes[way].ignored && <p className="text-label text-ink-soft">{flow.notes[way].ignored}</p>}
      <Rejections items={flow.notes[way].rejected} />
      <PickedList flow={flow} way={way} />
    </div>
  );
}

function TextWay({ flow }: { flow: AddFlow }) {
  const over = flow.text.length > MAX_TEXT_CHARS;
  return (
    <div className="space-y-3">
      <ui.Field label="Tiêu đề">
        <ui.Input value={flow.title} maxLength={200} onChange={(event) => flow.setTitle(event.target.value)} />
      </ui.Field>
      <ui.Field label="Nội dung" hint="Có thể gõ Markdown: # tiêu đề, ## mục, bảng, danh sách.">
        <textarea
          rows={10}
          value={flow.text}
          onChange={(event) => flow.setText(event.target.value)}
          className={ui.FIELD_CLASS}
        />
      </ui.Field>
      <p className={`text-label ${over ? "text-danger" : "text-ink-soft"}`}>
        {flow.text.length.toLocaleString("vi-VN")} / {MAX_TEXT_CHARS.toLocaleString("vi-VN")} ký tự
      </p>
      {flow.text !== "" && flow.textProblem && <p role="alert" className="text-label text-danger">{flow.textProblem}</p>}
    </div>
  );
}

export function ChooseStep({ flow }: { flow: AddFlow }) {
  return (
    <div className="space-y-4">
      <div role="group" aria-label="Cách thêm" className="grid gap-2 sm:grid-cols-3">
        {WAYS.map((way) => (
          <WayCard key={way.id} way={way} active={flow.way === way.id} onPick={() => flow.setWay(way.id)} />
        ))}
      </div>
      {flow.way === "files" && (
        <Picker flow={flow} way="files">
          Kéo thả tệp vào đây, hoặc chọn nhiều tệp một lần.
        </Picker>
      )}
      {flow.way === "folder" && (
        <Picker flow={flow} way="folder">
          Chọn một thư mục: chỉ giữ các tệp {FILE_EXTENSIONS.join(" ")}, tệp khác được bỏ qua.
        </Picker>
      )}
      {flow.way === "text" && <TextWay flow={flow} />}
    </div>
  );
}
