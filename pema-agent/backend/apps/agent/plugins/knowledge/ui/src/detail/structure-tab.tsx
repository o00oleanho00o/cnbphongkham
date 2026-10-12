/** "Bản dựng cấu trúc": the Markdown the reader built, editable, with its outline; re-read from it, or split sections off. */
import { useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import type { OutlineNode, Source, SourceStructure } from "../types";
import { indentOf, isDirty, splitError, toggled } from "./detail-logic";
import { useAction } from "./use-action";

const INDENT = ["pl-0", "pl-3", "pl-6", "pl-9", "pl-12", "pl-14"] as const;

type Load = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; structure: SourceStructure };

export function StructureTab({
  source,
  contentKey,
  edited,
  onEdit,
  onSourceChanged,
  onSplit,
}: {
  source: Source;
  /** Changes when the saved text may have changed. */
  contentKey: string;
  /** What is typed in the box and not saved; null when nothing is. */
  edited: string | null;
  onEdit: (text: string | null) => void;
  onSourceChanged: (source: Source) => void;
  onSplit: (created: Source) => void;
}) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<number[]>([]);
  const [splitting, setSplitting] = useState(false);
  const { busy, error, run } = useAction();

  useEffect(() => {
    let stale = false;
    knowledge.structure(source.id).then(
      (structure) => {
        if (stale) return;
        setLoad({ kind: "ready", structure });
        setSelected([]);
      },
      (err: unknown) => !stale && setLoad({ kind: "error", message: messageOf(err) }),
    );
    return () => {
      stale = true;
    };
  }, [source.id, contentKey, attempt]);

  if (load.kind === "loading") return <ui.Empty>Đang tải bản dựng...</ui.Empty>;
  if (load.kind === "error") {
    return (
      <div className="space-y-3">
        <ui.Notice tone="danger">{load.message}</ui.Notice>
        <ui.Button
          variant="secondary"
          onClick={() => {
            setLoad({ kind: "loading" });
            setAttempt(attempt + 1);
          }}
        >
          Thử lại
        </ui.Button>
      </div>
    );
  }

  const { markdown, outline } = load.structure;
  const dirty = isDirty(edited, markdown);

  const reindexFromText = () =>
    run("save", async () => {
      onSourceChanged(await knowledge.saveStructure(source.id, edited ?? markdown));
      onEdit(null);
    });

  return (
    <div className="space-y-4">
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {dirty && (
        <ui.Notice tone="warning">
          Bạn đã sửa mà chưa nạp lại. Rời khỏi trang này sẽ mất các sửa đổi.
        </ui.Notice>
      )}
      {markdown === "" && <ui.Notice tone="info">Nguồn này chưa có bản dựng (chưa đọc được tài liệu).</ui.Notice>}
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <div className="lg:order-2">
          <Outline
            outline={outline}
            selected={selected}
            onToggle={(position) => setSelected(toggled(selected, position))}
            stale={dirty}
          />
        </div>
        <div className="space-y-3 lg:order-1">
          <ui.Field label="Markdown đã dựng" hint="Sửa tiêu đề (#, ##, ###), bảng và danh sách rồi nạp lại.">
            <textarea
              value={edited ?? markdown}
              spellCheck={false}
              onChange={(event) => onEdit(event.target.value)}
              className={`${ui.FIELD_CLASS} min-h-[28rem] resize-y font-mono text-small leading-relaxed`}
            />
          </ui.Field>
          <div className="flex flex-wrap gap-2">
            <ui.Button disabled={!dirty} busy={busy === "save"} onClick={reindexFromText}>
              Nạp lại từ bản này
            </ui.Button>
            <ui.Button variant="secondary" disabled={!dirty} onClick={() => onEdit(null)}>
              Bỏ sửa đổi
            </ui.Button>
            <ui.Button
              variant="secondary"
              disabled={dirty || selected.length === 0}
              onClick={() => setSplitting(true)}
            >
              Tách các mục đã chọn thành nguồn mới{selected.length > 0 ? ` (${selected.length})` : ""}
            </ui.Button>
          </div>
          {dirty && <p className="text-label text-ink-soft">Nạp lại hoặc bỏ sửa đổi trước khi tách mục.</p>}
        </div>
      </div>
      {splitting && (
        <SplitDialog
          source={source}
          sections={selected}
          onClose={() => setSplitting(false)}
          onDone={(created) => {
            setSplitting(false);
            onSplit(created);
          }}
        />
      )}
    </div>
  );
}

function Outline({
  outline,
  selected,
  stale,
  onToggle,
}: {
  outline: readonly OutlineNode[];
  selected: readonly number[];
  stale: boolean;
  onToggle: (position: number) => void;
}) {
  return (
    <div className="rounded-tile border border-line p-3">
      <p className="mb-2 text-micro font-semibold tracking-wider text-ink-soft uppercase">Cây tiêu đề</p>
      {stale && <p className="mb-2 text-label text-ink-soft">Theo bản đã lưu, chưa gồm phần bạn đang sửa.</p>}
      {outline.length === 0 ? (
        <p className="text-small text-ink-soft">Chưa có tiêu đề nào.</p>
      ) : (
        <ul className="max-h-[28rem] space-y-0.5 overflow-y-auto">
          {outline.map((node, position) => (
            // The position is the identity of a node: the split call names sections by it.
            <li key={position} className={INDENT[indentOf(node.level)]}>
              <label className="flex min-h-11 cursor-pointer items-start gap-2 py-1 sm:min-h-0">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={selected.includes(position)}
                  onChange={() => onToggle(position)}
                  aria-label={`Chọn mục ${node.title}`}
                />
                <span className="min-w-0">
                  <span className="block text-small break-words text-ink">{node.title}</span>
                  <span className="block text-micro text-ink-soft">
                    {node.chunks} đoạn · {node.chars} ký tự
                  </span>
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SplitDialog({
  source,
  sections,
  onClose,
  onDone,
}: {
  source: Source;
  sections: readonly number[];
  onClose: () => void;
  onDone: (created: Source) => void;
}) {
  const [title, setTitle] = useState("");
  const { busy, error, run } = useAction();
  const problem = splitError(title, sections);

  return (
    <ConfirmDialog
      title="Tách thành nguồn mới"
      onClose={onClose}
      actions={
        <>
          <ui.Button variant="secondary" onClick={onClose}>
            Hủy
          </ui.Button>
          <ui.Button
            disabled={problem !== null}
            busy={busy === "split"}
            onClick={() => run("split", async () => onDone(await knowledge.split(source.id, sections, title.trim())))}
          >
            Tách {sections.length} mục
          </ui.Button>
        </>
      }
    >
      <div className="space-y-3">
        <p>
          {sections.length} mục đã chọn (cùng các mục con) được chuyển khỏi &quot;{source.title}&quot; sang một nguồn
          mới. Nguồn mới dùng được ngay.
        </p>
        <ui.Field label="Tên nguồn mới">
          <ui.Input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} />
        </ui.Field>
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      </div>
    </ConfirmDialog>
  );
}
