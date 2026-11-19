/** Trả lời có kiểm: the customer's turns run the checked answer flow (search first, every number checked). */
import { useState } from "react";

import { knowledge } from "../client";
import { Switch } from "../parts";
import { ui } from "../sdk";
import { SectionCard, type SectionProps, useSectionRun } from "./section-card";

export function AnswerSection({ settings, onSaved }: SectionProps) {
  const saved = settings.answer;
  const [on, setOn] = useState(saved.graph === "on");
  const [reply, setReply] = useState(saved.unsure_reply);
  const { busy, message, run } = useSectionRun();
  const changed = on !== (saved.graph === "on") || reply.trim() !== saved.unsure_reply;
  const replyOk = reply.trim().length >= 1 && reply.trim().length <= 500;

  const save = () =>
    run("save", async () => {
      const next = await knowledge.saveSettings({ answer: { graph: on ? "on" : "off", unsure_reply: reply.trim() } });
      onSaved(next);
      setOn(next.answer.graph === "on");
      setReply(next.answer.unsure_reply);
      return { tone: "success", text: next.answer.graph === "on" ? "Đã bật trả lời có kiểm." : "Đã tắt trả lời có kiểm." };
    });

  return (
    <SectionCard
      title="Trả lời có kiểm"
      intro="Agent tìm trong kho trước khi trả lời, rồi code kiểm từng con số của câu trả lời với dữ kiện tìm được. Số không có trong dữ kiện thì agent viết lại; vẫn sai thì gửi câu bên dưới."
      saveDisabled={!changed || !replyOk}
      saveBusy={busy === "save"}
      onSave={() => void save()}
      message={message}
    >
      <Switch
        label="Trả lời có kiểm"
        hint="Mỗi câu trả lời có thể tốn thêm một đến ba lần gọi model khi phải tìm lại hoặc viết lại"
        checked={on}
        onChange={setOn}
      />
      <ui.Field label="Câu khi không chắc" hint="Gửi khi hai lần viết lại vẫn nêu con số không có trong dữ kiện (tối đa 500 ký tự)">
        <ui.Input aria-label="Câu khi không chắc" value={reply} maxLength={500} onChange={(event) => setReply(event.target.value)} />
      </ui.Field>
    </SectionCard>
  );
}
