/** "Nhập từ bảng": paste a CSV or Markdown table, look at what was read, then add or update the services. */
import { useState } from "react";

import { knowledge, messageOf } from "../client";
import { Chip, Sheet } from "../parts";
import { ui } from "../sdk";
import type { Service } from "../types";
import {
  type ImportRow,
  type TableProblem,
  createBody,
  importRows,
  importSummary,
  parseServiceTable,
  updateBody,
} from "./services-logic";

const SAMPLE = "code,name,aliases,description\nHORI,Bớt Hori,hori; bớt hori,Điều trị bớt Hori bằng laser";

interface Preview {
  rows: ImportRow[];
  problems: TableProblem[];
}

async function saveRow({ service, existing }: ImportRow): Promise<void> {
  if (existing) await knowledge.updateService(existing.id, updateBody(service, existing));
  else await knowledge.createService(createBody(service));
}

export function ImportSheet({
  existing,
  onClose,
  onDone,
}: {
  existing: readonly Service[];
  onClose: () => void;
  /** Called after the services were saved, with a sentence for the page. */
  onDone: (summary: string) => void;
}) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<"read" | "save" | "">("");

  async function read() {
    setBusy("read");
    setError("");
    try {
      const parsed = await knowledge.importServices(text);
      // The server lists what it could read; the lines it could not read are found by the same rules here.
      setPreview({ rows: importRows(parsed, existing), problems: parseServiceTable(text).problems });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy("");
    }
  }

  async function confirm(rows: readonly ImportRow[]) {
    setBusy("save");
    setError("");
    const results = await Promise.allSettled(rows.map(saveRow));
    const failed = results.filter((result) => result.status === "rejected");
    setBusy("");
    if (failed.length === 0) {
      onDone(importSummary(rows.length, 0));
      return;
    }
    setError(`${importSummary(rows.length - failed.length, failed.length)} Thử lại sau khi kiểm tra bảng.`);
  }

  function edit(next: string) {
    setText(next);
    setPreview(null);
  }

  return (
    <Sheet
      title="Nhập dịch vụ từ bảng"
      wide
      onClose={onClose}
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <ui.Button variant="secondary" onClick={onClose}>
            Đóng
          </ui.Button>
          {preview ? (
            <ui.Button busy={busy === "save"} disabled={preview.rows.length === 0} onClick={() => void confirm(preview.rows)}>
              {`Nhập ${preview.rows.length} dịch vụ`}
            </ui.Button>
          ) : (
            <ui.Button busy={busy === "read"} disabled={text.trim() === ""} onClick={() => void read()}>
              Đọc bảng
            </ui.Button>
          )}
        </div>
      }
    >
      <p className="text-small text-ink-soft">
        Dán bảng CSV hoặc bảng Markdown với các cột: mã, tên, tên gọi khác (cách nhau bằng dấu ; hoặc ,), mô tả, chi nhánh
        (tùy chọn). Mã đã có thì dịch vụ được cập nhật, thêm tên gọi khác mới; mã mới thì tạo mới.
      </p>
      <ui.Field label="Nội dung bảng">
        <textarea
          value={text}
          rows={7}
          placeholder={SAMPLE}
          spellCheck={false}
          onChange={(event) => edit(event.target.value)}
          className={`${ui.FIELD_CLASS} font-mono`}
        />
      </ui.Field>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {preview && <ImportPreview preview={preview} />}
    </Sheet>
  );
}

function ImportPreview({ preview }: { preview: Preview }) {
  return (
    <div className="space-y-3">
      {preview.rows.length === 0 && <ui.Notice tone="warning">Không đọc được dòng nào. Kiểm tra lại cột và dòng đầu.</ui.Notice>}
      {preview.rows.length > 0 && (
        <ul aria-label="Dịch vụ đọc được" className="divide-y divide-line rounded-tile border border-line">
          {preview.rows.map(({ service, existing }) => (
            <li key={service.code} className="space-y-1 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-small font-semibold text-ink">{service.code}</span>
                <span className="text-body text-ink">{service.name}</span>
                <ui.Badge tone={existing ? "warning" : "success"}>{existing ? "Cập nhật" : "Mới"}</ui.Badge>
              </div>
              {service.aliases.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {service.aliases.map((alias) => (
                    <Chip key={alias}>{alias}</Chip>
                  ))}
                </div>
              )}
              {service.description && <p className="text-label text-ink-soft">{service.description}</p>}
            </li>
          ))}
        </ul>
      )}
      {preview.problems.length > 0 && (
        <div className="space-y-1">
          <p className="text-small font-medium text-danger">{`${preview.problems.length} dòng không đọc được, sẽ bị bỏ qua`}</p>
          <ul aria-label="Dòng không đọc được" className="space-y-1">
            {preview.problems.map((problem) => (
              <li key={problem.line} className="rounded-tile border border-danger-line bg-danger-soft px-3 py-2 text-label">
                <span className="font-semibold text-danger">{`Dòng ${problem.line}: `}</span>
                <span className="text-ink">{problem.reason}</span>
                <span className="mt-0.5 block break-all font-mono text-ink-soft">{problem.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
