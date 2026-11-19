/** "Câu hỏi chưa có tài liệu": what customers asked that the store could not answer, to be written up or set aside. */
import { useCallback, useEffect, useState } from "react";

import { AddSourceSheet } from "../add/add-source";
import { knowledge, messageOf } from "../client";
import { GapRow } from "../gaps/gap-row";
import { GAPS_EMPTY_HINT, GAP_FILTERS, answerDraft, emptyTitle, withoutGap } from "../gaps/gaps-logic";
import { ui } from "../sdk";
import type { Gap, GapState } from "../types";

function Filter({ value, onChange }: { value: GapState; onChange: (next: GapState) => void }) {
  return (
    <div role="radiogroup" aria-label="Lọc câu hỏi" className="inline-flex overflow-hidden rounded-control border border-line">
      {GAP_FILTERS.map((item) => (
        <button
          key={item.id}
          type="button"
          role="radio"
          aria-checked={item.id === value}
          onClick={() => onChange(item.id)}
          className={`min-h-11 px-4 py-2 text-body whitespace-nowrap sm:min-h-0 ${
            item.id === value ? "bg-brand-500 font-medium text-white" : "bg-surface text-ink hover:bg-tile"
          }`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

export function GapsPage() {
  const [state, setState] = useState<GapState>("open");
  const [gaps, setGaps] = useState<Gap[] | null>(null);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [writing, setWriting] = useState<Gap | null>(null);

  const load = useCallback(async (which: GapState) => {
    setError("");
    try {
      setGaps(await knowledge.gaps(which));
    } catch (err) {
      setError(messageOf(err));
      setGaps([]);
    }
  }, []);

  useEffect(() => {
    setGaps(null);
    void load(state);
  }, [state, load]);

  async function move(gap: Gap, next: GapState) {
    setBusyId(gap.id);
    setActionError("");
    try {
      await knowledge.updateGap(gap.id, next);
      setGaps((before) => (before ? withoutGap(before, gap.id) : before));
      await load(state);
    } catch (err) {
      setActionError(messageOf(err));
    } finally {
      setBusyId("");
    }
  }

  const draft = writing ? answerDraft(writing.question) : undefined;

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Câu hỏi chưa có tài liệu"
        subtitle="Những câu khách hỏi mà agent tra kho không ra kết quả đủ tốt."
        aside={<Filter value={state} onChange={setState} />}
      />
      {error && (
        <ui.Notice tone="danger">
          <span className="flex flex-wrap items-center justify-between gap-2">
            {error}
            <ui.Button variant="secondary" onClick={() => void load(state)}>
              Thử lại
            </ui.Button>
          </span>
        </ui.Notice>
      )}
      {actionError && <ui.Notice tone="danger">{actionError}</ui.Notice>}
      {gaps === null && <p className="py-6 text-center text-small text-ink-soft">Đang tải…</p>}
      {gaps !== null && gaps.length === 0 && !error && (
        <ui.Card>
          <p className="text-center text-body font-bold text-heading">{emptyTitle(state)}</p>
          {state === "open" && <ui.Empty>{GAPS_EMPTY_HINT}</ui.Empty>}
        </ui.Card>
      )}
      {gaps !== null && gaps.length > 0 && (
        <ul className="space-y-2">
          {gaps.map((gap) => (
            <GapRow
              key={gap.id}
              gap={gap}
              busy={busyId === gap.id}
              onWrite={() => setWriting(gap)}
              onIgnore={() => void move(gap, "ignored")}
              onReopen={() => void move(gap, "open")}
            />
          ))}
        </ul>
      )}
      {writing && draft && (
        <AddSourceSheet
          initial={draft}
          onClose={() => setWriting(null)}
          onAdded={() => {
            const gap = writing;
            setWriting(null);
            void move(gap, "answered");
          }}
        />
      )}
    </div>
  );
}
