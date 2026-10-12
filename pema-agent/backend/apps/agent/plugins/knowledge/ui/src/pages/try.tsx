/** "Thử tìm": ask a question the way a channel would and see what every stage of the search did. */
import { type FormEvent, type KeyboardEvent, useState } from "react";

import { knowledge, messageOf } from "../client";
import { todayIso } from "../logic";
import { ui } from "../sdk";
import type { SearchDebug, SearchDebugQuery } from "../types";
import { ResultView } from "../try/result-view";
import { CHANNEL_OPTIONS, PATIENT_CHANNEL_HINT, isBlankQuestion } from "../try/try-logic";
import { useStoreNav } from "./store";

export function TryPage() {
  const nav = useStoreNav();
  const [question, setQuestion] = useState("");
  const [channel, setChannel] = useState<SearchDebugQuery["channel"]>("patient");
  const [asOf, setAsOf] = useState(() => todayIso());
  const [result, setResult] = useState<SearchDebug | null>(null);
  /** Counts the runs, so a new result starts with its stages closed again. */
  const [run, setRun] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const canRun = !isBlankQuestion(question) && asOf !== "";

  async function search() {
    if (!canRun || busy) return;
    setBusy(true);
    setError("");
    try {
      setResult(await knowledge.search({ question: question.trim(), channel, as_of: asOf }));
      setRun((before) => before + 1);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void search();
  }

  function askOnCtrlEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    void search();
  }

  return (
    <div className="space-y-4">
      <ui.PageHeader title="Thử tìm" subtitle="Xem agent sẽ tìm được gì cho một câu hỏi, từng bước một." />
      <form onSubmit={submit}>
        <ui.Card>
          <div className="space-y-4">
            <ui.Field label="Câu hỏi" hint="Gõ như khách hỏi. Ctrl + Enter để tìm.">
              <textarea
                className={`${ui.FIELD_CLASS} min-h-24 resize-y`}
                rows={3}
                value={question}
                maxLength={500}
                placeholder="vd: trị nám bao nhiêu tiền?"
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={askOnCtrlEnter}
              />
            </ui.Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <ui.Field label="Như kênh">
                <ui.Select
                  value={channel}
                  onChange={(event) => setChannel(event.target.value === "staff" ? "staff" : "patient")}
                  options={CHANNEL_OPTIONS}
                />
              </ui.Field>
              <ui.Field label="Ngày hỏi" hint="Giá và quy định có hiệu lực vào ngày này.">
                <ui.Input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
              </ui.Field>
            </div>
            {channel === "patient" && <ui.Notice tone="info">{PATIENT_CHANNEL_HINT}</ui.Notice>}
            {error && (
              <ui.Notice tone="danger">
                {error}
              </ui.Notice>
            )}
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={!canRun || busy}
                className="inline-flex min-h-11 items-center justify-center rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white transition-colors hover:bg-brand-600 disabled:opacity-50 max-sm:w-full sm:min-h-0"
              >
                {busy ? "Đang tìm…" : "Thử tìm"}
              </button>
            </div>
          </div>
        </ui.Card>
      </form>
      {result === null && !busy && !error && (
        <ui.Empty>Nhập một câu hỏi rồi bấm "Thử tìm" để xem từng bước tìm kiếm.</ui.Empty>
      )}
      {result && (
        <ResultView key={run} result={result} onOpenSource={(source) => nav.go("sources", { source })} />
      )}
    </div>
  );
}
