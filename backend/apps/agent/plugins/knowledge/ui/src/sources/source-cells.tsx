/** The small pieces of one source's row, shared by the table and the phone cards. */
import {
  AUDIENCE_LABEL,
  LIFECYCLE_LABEL,
  LIFECYCLE_TONE,
  PROCESSING_LABEL,
  PROCESSING_TONE,
  formatDate,
  periodText,
  progressPercent,
  progressText,
} from "../logic";
import { Chip, ProgressBar } from "../parts";
import { ui } from "../sdk";
import type { Source } from "../types";
import { approvalWho, kindText } from "./sources-logic";

export function TitleCell({ source, onOpen }: { source: Source; onOpen: () => void }) {
  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={onOpen}
        className="text-left text-body font-medium break-words text-link hover:underline"
      >
        {source.title}
      </button>
      {source.doc_code && <p className="font-mono text-micro break-all text-ink-soft">{source.doc_code}</p>}
    </div>
  );
}

export function KindCell({ source }: { source: Source }) {
  const { kind, format } = kindText(source);
  return (
    <div>
      <p className="text-small text-ink">{kind}</p>
      <p className="text-micro text-ink-soft">{format}</p>
    </div>
  );
}

export function ServicesCell({ source, names }: { source: Source; names: ReadonlyMap<string, string> }) {
  if (source.services.length === 0) return <span className="text-small text-ink-soft">Tự nhận diện</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {source.services.map((code) => (
        <Chip key={code}>{names.get(code) ?? code}</Chip>
      ))}
    </div>
  );
}

export function AudienceCell({ source }: { source: Source }) {
  return <ui.Badge tone={source.audience === "patient" ? "info" : "neutral"}>{AUDIENCE_LABEL[source.audience]}</ui.Badge>;
}

/** The state of the reading: a bar and the stage line while it runs, the sentence when it failed. */
export function ProcessingCell({ source }: { source: Source }) {
  const running = source.processing === "queued" || source.processing === "processing";
  return (
    <div className="space-y-1">
      <ui.Badge tone={PROCESSING_TONE[source.processing]}>{PROCESSING_LABEL[source.processing]}</ui.Badge>
      {running && (
        <>
          <ProgressBar percent={progressPercent(source.progress)} label={`Tiến độ nạp ${source.title}`} />
          <p className="text-micro text-ink-soft">{progressText(source.progress)}</p>
        </>
      )}
      {source.processing === "error" && source.error && <p className="text-label text-danger">{source.error}</p>}
    </div>
  );
}

export function LifecycleCell({ source }: { source: Source }) {
  return (
    <div className="space-y-1">
      <ui.Badge tone={LIFECYCLE_TONE[source.lifecycle]}>{LIFECYCLE_LABEL[source.lifecycle]}</ui.Badge>
      <p className="text-micro text-ink-soft">{periodText(source.effective_from, source.effective_to)}</p>
    </div>
  );
}

export function ApprovalCell({ source }: { source: Source }) {
  if (!source.approved) return <ui.Badge tone="warning">Chưa</ui.Badge>;
  return (
    <div className="space-y-1">
      <ui.Badge tone="success">Có</ui.Badge>
      <p className="text-micro text-ink-soft">{approvalWho(source)}</p>
    </div>
  );
}

export function UpdatedCell({ source }: { source: Source }) {
  return <span className="text-small whitespace-nowrap text-ink-soft">{formatDate(source.updated_at)}</span>;
}
