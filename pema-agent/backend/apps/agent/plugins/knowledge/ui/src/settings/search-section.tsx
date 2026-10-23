/** Tìm kiếm: how many results, the minimum score and the character budget. */
import { useState } from "react";

import { knowledge } from "../client";
import { ui } from "../sdk";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import { RANGES, type SearchForm, hasProblems, searchChange, searchFormOf, searchProblems } from "./settings-logic";

const rangeHint = (range: { min: number; max: number }) => `Từ ${range.min} đến ${range.max}`;

export function SearchSection({ settings, onSaved }: SectionProps) {
  const saved = settings.search;
  const [form, setForm] = useState<SearchForm>(() => searchFormOf(saved));
  const { busy, message, run } = useSectionRun();

  const problems = searchProblems(form);
  const change = searchChange(form, saved);
  const set = <K extends keyof SearchForm>(key: K, value: SearchForm[K]) =>
    setForm((before) => ({ ...before, [key]: value }));
  const shown = (field: keyof typeof problems) => (change ? problems[field] : undefined);

  const save = () =>
    run("save", async () => {
      if (!change) return null;
      if (hasProblems(problems)) return { tone: "danger", text: "Sửa các ô báo lỗi rồi lưu lại." };
      const next = await knowledge.saveSettings(change);
      onSaved(next);
      setForm(searchFormOf(next.search));
      return { tone: "success", text: "Đã lưu cài đặt tìm kiếm." };
    });

  return (
    <SectionCard
      title="Tìm kiếm"
      saveDisabled={change === null}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <ui.Field label="Số kết quả" hint={rangeHint(RANGES.results)} error={shown("results")}>
          <ui.Input inputMode="numeric" value={form.results} onChange={(event) => set("results", event.target.value)} />
        </ui.Field>
        <ui.Field label="Điểm tối thiểu" hint="Độ giống tối thiểu (0 đến 1) của kết quả tìm theo nghĩa; mặc định 0,35" error={shown("min_score")}>
          <ui.Input inputMode="decimal" value={form.min_score} onChange={(event) => set("min_score", event.target.value)} />
        </ui.Field>
        <ui.Field label="Ngân sách ký tự" hint="Tổng độ dài chữ đưa cho agent" error={shown("char_budget")}>
          <ui.Input inputMode="numeric" value={form.char_budget} onChange={(event) => set("char_budget", event.target.value)} />
        </ui.Field>
      </div>
    </SectionCard>
  );
}
