/** Gán nhãn và xếp lại: switches for the two model steps and the chat model they use. */
import { useEffect, useState } from "react";

import { knowledge, modelChoices } from "../client";
import { Switch } from "../parts";
import { ui } from "../sdk";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import { type LabellingForm, labellingChange, modelEntry, modelOptions, modelValue } from "./settings-logic";

export function LabellingSection({ settings, onSaved }: SectionProps) {
  const saved = settings.labelling;
  const [form, setForm] = useState<LabellingForm>(saved);
  const [choices, setChoices] = useState<{ id: string; label: string }[] | null>(null);
  const { busy, message, run } = useSectionRun();

  useEffect(() => {
    modelChoices().then(setChoices, () => setChoices([]));
  }, []);

  const change = labellingChange(form, saved);

  const save = () =>
    run("save", async () => {
      if (!change) return null;
      const next = await knowledge.saveSettings(change);
      onSaved(next);
      setForm(next.labelling);
      return { tone: "success", text: "Đã lưu cách gán nhãn và xếp lại." };
    });

  const set = <K extends keyof LabellingForm>(key: K, value: LabellingForm[K]) =>
    setForm((before) => ({ ...before, [key]: value }));

  return (
    <SectionCard
      title="Gán nhãn và xếp lại"
      intro="Hai bước dùng model chat: gán nhãn dịch vụ và loại cho từng đoạn khi nạp, và xếp lại kết quả tìm."
      saveDisabled={change === null}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      <Switch
        label="Gán nhãn đoạn khi nạp"
        hint="Tắt thì đoạn không có nhãn, tìm kiếm kém chính xác hơn"
        checked={form.enabled}
        onChange={(next) => set("enabled", next)}
      />
      <Switch
        label="Xếp lại kết quả tìm"
        hint="Model chấm lại các kết quả gần nhất; chậm hơn một chút"
        checked={form.rerank}
        onChange={(next) => set("rerank", next)}
      />
      <ui.Field
        label="Model chat dùng cho hai bước này"
        hint={choices === null ? "Đang tải danh sách model…" : "Chọn trong danh sách ở trang Model"}
      >
        <ui.Select
          options={modelOptions(choices ?? [], form.model_entry)}
          value={modelValue(form.model_entry)}
          onChange={(event) => set("model_entry", modelEntry(event.target.value))}
        />
      </ui.Field>
    </SectionCard>
  );
}
