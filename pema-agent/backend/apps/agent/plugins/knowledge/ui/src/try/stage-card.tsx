/** One stage of a search trial as a card that opens and closes; its candidates in rank order. */
import { useId, useState } from "react";

import { ui } from "../sdk";
import type { Candidate, SearchStage } from "../types";
import { formatMs, formatScore, listsCandidates, scoreLabel, sourceIdOf, stageCount, stageSummary, startsOpen } from "./try-logic";

function CandidateRow({
  rank,
  stageId,
  candidate,
  onOpenSource,
}: {
  rank: number;
  stageId: string;
  candidate: Candidate;
  onOpenSource: (sourceId: string) => void;
}) {
  const sourceId = sourceIdOf(candidate.chunk_id);
  return (
    <li className="flex gap-3 rounded-tile border border-line bg-surface px-3 py-2.5">
      <span className="w-6 shrink-0 text-right text-small font-bold text-ink-soft">{rank}</span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {sourceId ? (
            <button
              type="button"
              onClick={() => onOpenSource(sourceId)}
              className="min-h-11 text-left text-small font-bold break-words text-link hover:underline sm:min-h-0"
            >
              {candidate.source_title}
            </button>
          ) : (
            <span className="text-small font-bold break-words text-ink">{candidate.source_title}</span>
          )}
          {candidate.doc_code && <ui.Badge>{candidate.doc_code}</ui.Badge>}
        </div>
        <p className="text-label break-words text-ink-soft">{candidate.path}</p>
        <p className="text-small break-words whitespace-pre-line text-ink">{candidate.excerpt}</p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-small font-bold text-heading">{formatScore(stageId, candidate.score)}</p>
        <p className="text-micro text-ink-soft">{scoreLabel(stageId)}</p>
      </div>
    </li>
  );
}

export function StageCard({
  stage,
  onOpenSource,
}: {
  stage: SearchStage;
  onOpenSource: (sourceId: string) => void;
}) {
  const [open, setOpen] = useState(startsOpen(stage.id));
  const bodyId = useId();
  const summary = stageSummary(stage);
  const count = stageCount(stage);
  return (
    <section className={`rounded-card border border-line bg-surface shadow-card ${stage.skipped ? "opacity-70" : ""}`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={bodyId}
        onClick={() => setOpen((before) => !before)}
        className="flex min-h-11 w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span aria-hidden className="w-4 shrink-0 text-ink-soft">
          {open ? "▾" : "▸"}
        </span>
        <span className="min-w-0 flex-1 text-body font-bold break-words text-heading">{stage.title}</span>
        {count && <ui.Badge tone={stage.skipped ? "warning" : "neutral"}>{count}</ui.Badge>}
        <span className="shrink-0 text-label text-ink-soft">{formatMs(stage.ms)}</span>
      </button>
      {open && (
        <div id={bodyId} className="space-y-3 border-t border-line px-4 py-3">
          {summary && <p className={`text-small ${stage.skipped ? "text-warning" : "text-ink-soft"}`}>{summary}</p>}
          {listsCandidates(stage.id) && stage.candidates.length > 0 && (
            <ol className="space-y-2">
              {stage.candidates.map((candidate, index) => (
                <CandidateRow
                  key={candidate.chunk_id}
                  rank={index + 1}
                  stageId={stage.id}
                  candidate={candidate}
                  onOpenSource={onOpenSource}
                />
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  );
}
