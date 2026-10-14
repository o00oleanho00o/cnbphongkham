/** Xếp lại và lọc bằng Jev: before the agent reads what a search found, Jev rates each chunk; a switch and how strict. */
import { useEffect, useState } from "react";

import { jevState, knowledge } from "../client";
import { Switch } from "../parts";
import { ui } from "../sdk";
import type { JevState } from "../types";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import { type JudgingForm, LEVEL_OPTIONS, asLevel, jevNotice, judgingChange } from "./settings-logic";

export function JudgingSection({ settings, onSaved }: SectionProps) {
  const saved = settings.judging;
  const [form, setForm] = useState<JudgingForm>(saved);
  const [jev, setJev] = useState<JevState | null>(null);
  const { busy, message, run } = useSectionRun();

  useEffect(() => {
    jevState().then(setJev, () => setJev(null));
  }, []);

  const change = judgingChange(form, saved);
  const notice = jevNotice(jev);

  const save = () =>
    run("save", async () => {
      if (!change) return null;
      const next = await knowledge.saveSettings(change);
      onSaved(next);
      setForm(next.judging);
      return { tone: "success", text: "Đã lưu cách xếp lại và lọc." };
    });

  return (
    <SectionCard
      title="Xếp lại và lọc bằng Jev"
      intro="Trước khi agent đọc, Jev chấm lại các đoạn tìm được: bỏ đoạn lạc đề hoặc cố điều khiển trợ lý, bỏ đoạn không nêu đúng điều khách hỏi, xếp đoạn đúng nhất lên đầu. Không đoạn nào đủ căn cứ thì agent nói chưa có thông tin."
      saveDisabled={change === null}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      {notice && <ui.Notice tone="warning">{notice}</ui.Notice>}
      <Switch
        label="Xếp lại và lọc bằng Jev"
        hint="Câu tìm và nội dung các đoạn được gửi tới TypeSafe (Mỹ) để chấm; Jev lỗi hoặc chậm thì kết quả dùng như chưa lọc"
        checked={form.enabled}
        onChange={(enabled) => setForm((before) => ({ ...before, enabled }))}
      />
      <ui.Field label="Mức chặt" hint="Chặt thì ít đoạn lọt qua hơn, agent hay nói chưa có thông tin hơn">
        <ui.Select
          aria-label="Mức chặt của bộ lọc"
          options={LEVEL_OPTIONS.map(({ value, label }) => ({ value, label }))}
          value={form.level}
          onChange={(event) => setForm((before) => ({ ...before, level: asLevel(event.target.value) }))}
        />
      </ui.Field>
    </SectionCard>
  );
}
