/** Đọc tài liệu: which reader turns files into text, the Docling address and a connection test. */
import { useState } from "react";

import { knowledge } from "../client";
import { ui } from "../sdk";
import type { KnowledgeSettings } from "../types";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import {
  PARSER_OPTIONS,
  type ParserForm,
  hasProblems,
  parserChange,
  parserFormOf,
  parserProblems,
  parserTestText,
  resetChange,
} from "./settings-logic";

function isKind(value: string): value is ParserForm["kind"] {
  return PARSER_OPTIONS.some((option) => option.value === value);
}

export function ParserSection({ settings, onSaved }: SectionProps) {
  const saved = settings.parser;
  const [form, setForm] = useState<ParserForm>(() => parserFormOf(saved));
  const { busy, message, run } = useSectionRun();

  const problems = parserProblems(form);
  const change = parserChange(form, saved);

  const take = (next: KnowledgeSettings) => {
    onSaved(next);
    setForm(parserFormOf(next.parser));
  };

  const save = () =>
    run("save", async () => {
      if (!change) return null;
      if (hasProblems(problems)) return { tone: "danger", text: "Sửa ô báo lỗi rồi lưu lại." };
      take(await knowledge.saveSettings(change));
      return { tone: "success", text: "Đã lưu cách đọc tài liệu." };
    });

  const reset = () =>
    run("reset", async () => {
      take(await knowledge.saveSettings(resetChange("parser")));
      return { tone: "info", text: "Đã về cấu hình mặc định của agent." };
    });

  const test = () =>
    run("test", async () => {
      const result = await knowledge.testParser();
      return { tone: result.ok ? "success" : "danger", text: parserTestText(result) };
    });

  return (
    <SectionCard
      title="Đọc tài liệu"
      origin={saved.origin}
      onReset={() => void reset()}
      resetBusy={busy === "reset"}
      saveDisabled={change === null}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <ui.Field label="Cách đọc">
          <ui.Select
            options={PARSER_OPTIONS}
            value={form.kind}
            onChange={(event) => {
              const kind = event.target.value;
              if (isKind(kind)) setForm((before) => ({ ...before, kind }));
            }}
          />
        </ui.Field>
        <ui.Field
          label="Địa chỉ Docling"
          hint="Cần khi chọn Docling"
          error={change ? problems.docling_url : undefined}
        >
          <ui.Input
            type="url"
            value={form.docling_url}
            placeholder="http://docling:5001"
            onChange={(event) => setForm((before) => ({ ...before, docling_url: event.target.value }))}
          />
        </ui.Field>
      </div>
      <div className="space-y-2">
        <ui.Button variant="secondary" busy={busy === "test"} onClick={() => void test()}>
          Kiểm tra kết nối
        </ui.Button>
        {change && <p className="text-label text-ink-soft">Kiểm tra kết nối dùng giá trị đã lưu: lưu thay đổi trước khi kiểm tra.</p>}
      </div>
    </SectionCard>
  );
}
