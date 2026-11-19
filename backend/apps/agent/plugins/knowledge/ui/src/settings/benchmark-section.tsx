/** Benchmark: a switch that lets challenge documents in; off in normal use. */
import { useState } from "react";

import { knowledge } from "../client";
import { Switch } from "../parts";
import { ui } from "../sdk";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";
import { BENCHMARK_NOTICE } from "./settings-logic";

export function BenchmarkSection({ settings, onSaved }: SectionProps) {
  const saved = settings.benchmark_mode;
  const [on, setOn] = useState(saved);
  const { busy, message, run } = useSectionRun();

  const save = () =>
    run("save", async () => {
      const next = await knowledge.saveSettings({ benchmark_mode: on });
      onSaved(next);
      setOn(next.benchmark_mode);
      return { tone: "success", text: next.benchmark_mode ? "Đã bật chế độ benchmark." : "Đã tắt chế độ benchmark." };
    });

  return (
    <SectionCard
      title="Benchmark"
      saveDisabled={on === saved}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      <Switch label="Chế độ benchmark" checked={on} onChange={setOn} />
      <ui.Notice tone={on ? "warning" : "info"}>{BENCHMARK_NOTICE}</ui.Notice>
    </SectionCard>
  );
}
