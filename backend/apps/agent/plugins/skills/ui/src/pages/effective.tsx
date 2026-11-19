/** "Kênh nhận gì": for a channel, which items apply (broad first) and the text its next question will carry. */
import { useState } from "react";

import { messageOf, skills } from "../client";
import { KIND_LABEL, rankLabel, scopesSummary } from "../logic";
import { ui } from "../sdk";
import type { Choices, Effective } from "../types";

export function EffectivePage({ choices }: { choices: Choices }) {
  const [channel, setChannel] = useState("");
  const [result, setResult] = useState<Effective | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function look() {
    setBusy(true);
    setError("");
    try {
      setResult(await skills.effective(channel.trim()));
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Kênh nhận gì"
        subtitle="Chọn một kênh (một tài khoản) để xem các mục áp dụng cho nó, theo thứ tự agent đọc: chung trước, riêng sau."
      />
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <ui.Field label="Kênh" hint="Để trống để xem phần áp dụng cho cả agent.">
            <ui.Input
              list="skills-channels"
              placeholder="ví dụ zalo-123"
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            />
          </ui.Field>
          <datalist id="skills-channels">
            {choices.channels.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </div>
        <ui.Button busy={busy} onClick={() => void look()}>
          Xem
        </ui.Button>
      </div>
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      {result && (
        <>
          <ui.Card title={result.channel ? `Kênh ${result.channel}` : "Cả agent"}>
            {result.plugin && <p className="mb-3 text-small text-ink-soft">Kênh này thuộc plugin {result.plugin}.</p>}
            {result.items.length === 0 && <ui.Empty>Kênh này chưa nhận mục nào.</ui.Empty>}
            <ol className="space-y-1.5">
              {result.items.map((item, index) => (
                <li key={item.id} className="flex flex-wrap items-center gap-2 text-body text-ink">
                  <span className="text-small text-ink-soft">{index + 1}.</span>
                  <span className="font-bold text-heading">{item.name}</span>
                  <ui.Badge>{KIND_LABEL[item.kind]}</ui.Badge>
                  <ui.Badge tone="info">{rankLabel(item.rank)}</ui.Badge>
                  <span className="text-small text-ink-soft">{scopesSummary(item.scopes)}</span>
                </li>
              ))}
            </ol>
          </ui.Card>
          {result.text && (
            <ui.Card title="Văn bản agent nhận ở mỗi câu hỏi">
              <pre className="max-h-[32rem] overflow-auto rounded-tile border border-line bg-tile p-3 text-small whitespace-pre-wrap text-ink">
                {result.text}
              </pre>
            </ui.Card>
          )}
        </>
      )}
    </div>
  );
}
