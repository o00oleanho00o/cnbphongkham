/** Embedding: the provider, the key (never shown back), a connection test and re-embedding every chunk. */
import { useState } from "react";

import { knowledge } from "../client";
import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import type { KnowledgeSettings } from "../types";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import {
  type EmbeddingForm,
  type KeyEdit,
  embeddingChange,
  embeddingFormOf,
  embeddingProblems,
  embeddingState,
  embeddingTestText,
  hasProblems,
  keyEditOf,
  reembedDone,
  reembedWarning,
  resetChange,
} from "./settings-logic";

function KeyField({
  hasKey,
  edit,
  onChange,
}: {
  hasKey: boolean;
  edit: KeyEdit;
  onChange: (next: KeyEdit) => void;
}) {
  if (hasKey && edit.mode !== "typing") {
    const removing = edit.mode === "removing";
    return (
      <div>
        <p className="mb-1 text-small font-medium text-ink">Khóa API</p>
        <div className="flex flex-wrap items-center gap-2">
          <ui.Badge tone={removing ? "warning" : "success"}>{removing ? "Sẽ xóa khóa khi lưu" : "Đã lưu khóa"}</ui.Badge>
          {removing ? (
            <ui.Button variant="ghost" onClick={() => onChange(keyEditOf(true))}>
              Giữ khóa
            </ui.Button>
          ) : (
            <>
              <ui.Button variant="ghost" onClick={() => onChange({ mode: "typing", typed: "" })}>
                Đổi khóa
              </ui.Button>
              <ui.Button variant="ghost" onClick={() => onChange({ mode: "removing", typed: "" })}>
                Xóa khóa
              </ui.Button>
            </>
          )}
        </div>
        <p className="mt-1 text-label text-ink-soft">Khóa được mã hóa và không bao giờ hiện lại.</p>
      </div>
    );
  }
  return (
    <ui.Field
      label="Khóa API"
      hint={
        hasKey
          ? "Gõ khóa mới để thay khóa đang lưu. Khóa được mã hóa và không bao giờ hiện lại."
          : "Chưa có khóa. Khóa được mã hóa và không bao giờ hiện lại."
      }
    >
      <div className="flex flex-wrap gap-2">
        <ui.Input
          type="password"
          autoComplete="off"
          className="min-w-0 flex-1"
          value={edit.typed}
          onChange={(event) => onChange({ mode: "typing", typed: event.target.value })}
        />
        {hasKey && (
          <ui.Button variant="secondary" onClick={() => onChange(keyEditOf(true))}>
            Giữ khóa cũ
          </ui.Button>
        )}
      </div>
    </ui.Field>
  );
}

export function EmbeddingSection({ settings, onSaved }: SectionProps) {
  const saved = settings.embedding;
  const [form, setForm] = useState<EmbeddingForm>(() => embeddingFormOf(saved));
  const [key, setKey] = useState<KeyEdit>(() => keyEditOf(saved.has_key));
  const [asking, setAsking] = useState(false);
  const { busy, message, run } = useSectionRun();

  const problems = embeddingProblems(form);
  const change = embeddingChange(form, saved, key);
  const set = (field: keyof EmbeddingForm) => (value: string) => setForm((before) => ({ ...before, [field]: value }));

  const take = (next: KnowledgeSettings) => {
    onSaved(next);
    setForm(embeddingFormOf(next.embedding));
    setKey(keyEditOf(next.embedding.has_key));
  };

  const save = () =>
    run("save", async () => {
      if (!change) return null;
      if (hasProblems(problems)) return { tone: "danger", text: "Sửa các ô báo lỗi rồi lưu lại." };
      take(await knowledge.saveSettings(change));
      return { tone: "success", text: "Đã lưu cài đặt embedding." };
    });

  const reset = () =>
    run("reset", async () => {
      take(await knowledge.saveSettings(resetChange("embedding")));
      return { tone: "info", text: "Đã về cấu hình mặc định của agent." };
    });

  const test = () =>
    run("test", async () => {
      const result = await knowledge.testEmbedding();
      return { tone: result.ok ? "success" : "danger", text: embeddingTestText(result, saved.dimensions) };
    });

  const reembed = () => {
    setAsking(false);
    return run("reembed", async () => {
      const { queued } = await knowledge.reembed();
      onSaved(await knowledge.settings());
      return { tone: "success", text: reembedDone(queued) };
    });
  };

  const showError = (field: keyof typeof problems) => (change ? problems[field] : undefined);

  return (
    <>
      <SectionCard
        title="Embedding"
        intro="Dịch vụ biến câu chữ thành vector để tìm theo nghĩa (OpenAI-compatible)."
        origin={saved.origin}
        onReset={() => void reset()}
        resetBusy={busy === "reset"}
        saveDisabled={change === null}
        saveBusy={busy === "save"}
        onSave={() => void save()}
        message={message}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <ui.Field label="Địa chỉ (base URL)" error={showError("base_url")}>
            <ui.Input
              type="url"
              value={form.base_url}
              placeholder="https://api.example.test/v1"
              onChange={(event) => set("base_url")(event.target.value)}
            />
          </ui.Field>
          <ui.Field label="Model" error={showError("model")}>
            <ui.Input value={form.model} onChange={(event) => set("model")(event.target.value)} />
          </ui.Field>
          <ui.Field label="Số chiều" hint="Phải khớp số chiều của model" error={showError("dimensions")}>
            <ui.Input inputMode="numeric" value={form.dimensions} onChange={(event) => set("dimensions")(event.target.value)} />
          </ui.Field>
          <KeyField hasKey={saved.has_key} edit={key} onChange={setKey} />
          <ui.Field label="Tiền tố câu hỏi" hint="Một số model cần chữ đứng trước câu hỏi; để trống nếu không">
            <ui.Input value={form.query_prefix} onChange={(event) => set("query_prefix")(event.target.value)} />
          </ui.Field>
          <ui.Field label="Tiền tố tài liệu" hint="Chữ đứng trước mỗi đoạn khi nhúng; để trống nếu không">
            <ui.Input value={form.document_prefix} onChange={(event) => set("document_prefix")(event.target.value)} />
          </ui.Field>
        </div>
        <div className="space-y-2 rounded-tile border border-line p-3">
          <p className="text-small text-ink">{embeddingState(saved)}</p>
          <div className="flex flex-wrap gap-2">
            <ui.Button variant="secondary" busy={busy === "test"} onClick={() => void test()}>
              Kiểm tra kết nối
            </ui.Button>
            <ui.Button variant="secondary" busy={busy === "reembed"} onClick={() => setAsking(true)}>
              Nhúng lại toàn bộ
            </ui.Button>
          </div>
          {change && (
            <p className="text-label text-ink-soft">Kiểm tra kết nối dùng giá trị đã lưu: lưu thay đổi trước khi kiểm tra.</p>
          )}
        </div>
      </SectionCard>
      {asking && (
        <ConfirmDialog
          title="Nhúng lại toàn bộ?"
          onClose={() => setAsking(false)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setAsking(false)}>
                Hủy
              </ui.Button>
              <ui.Button onClick={() => void reembed()}>Nhúng lại</ui.Button>
            </>
          }
        >
          {reembedWarning(saved)}
        </ConfirmDialog>
      )}
    </>
  );
}
