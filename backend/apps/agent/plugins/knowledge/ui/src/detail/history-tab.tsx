/** "Lịch sử": what happened to a source, newest first, with a way back to an earlier text. */
import { useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import { formatDate } from "../logic";
import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import type { Source, SourceEvent } from "../types";
import { canRestore, eventLabel, eventTone } from "./detail-logic";
import { useAction } from "./use-action";

type Load = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ready"; events: SourceEvent[] };

/** `2026-10-12T08:30:00+07:00` as `12/10/2026 08:30`. */
function whenText(at: string): string {
  const time = /T(\d{2}:\d{2})/.exec(at)?.[1];
  return time ? `${formatDate(at)} ${time}` : formatDate(at);
}

export function HistoryTab({
  sourceId,
  contentKey,
  onRestored,
}: {
  sourceId: string;
  contentKey: string;
  onRestored: (source: Source) => void;
}) {
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [restoring, setRestoring] = useState<SourceEvent | null>(null);
  const { busy, error, run } = useAction();

  useEffect(() => {
    let stale = false;
    knowledge.events(sourceId).then(
      (events) => !stale && setLoad({ kind: "ready", events }),
      (err: unknown) => !stale && setLoad({ kind: "error", message: messageOf(err) }),
    );
    return () => {
      stale = true;
    };
  }, [sourceId, contentKey, attempt]);

  if (load.kind === "loading") return <ui.Empty>Đang tải lịch sử...</ui.Empty>;
  if (load.kind === "error") {
    return (
      <div className="space-y-3">
        <ui.Notice tone="danger">{load.message}</ui.Notice>
        <ui.Button
          variant="secondary"
          onClick={() => {
            setLoad({ kind: "loading" });
            setAttempt(attempt + 1);
          }}
        >
          Thử lại
        </ui.Button>
      </div>
    );
  }
  if (load.events.length === 0) return <ui.Empty>Chưa có sự kiện nào.</ui.Empty>;

  async function restore(event: SourceEvent) {
    const done = await run("restore", async () => onRestored(await knowledge.restore(sourceId, event.id)));
    if (done) setRestoring(null);
  }

  return (
    <div className="space-y-3">
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <ol className="space-y-3 border-l border-line pl-4">
        {load.events.map((event) => (
          <li key={event.id} className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <ui.Badge tone={eventTone(event.kind)}>{eventLabel(event.kind)}</ui.Badge>
              <span className="text-small text-ink-soft">
                {event.by} · {whenText(event.at)}
              </span>
              {canRestore(event) && (
                <ui.Button variant="ghost" onClick={() => setRestoring(event)}>
                  Khôi phục bản này
                </ui.Button>
              )}
            </div>
            {event.note && <p className="text-small break-words text-ink">{event.note}</p>}
          </li>
        ))}
      </ol>
      {restoring && (
        <ConfirmDialog
          title="Khôi phục bản này?"
          onClose={() => setRestoring(null)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setRestoring(null)}>
                Không
              </ui.Button>
              <ui.Button busy={busy === "restore"} onClick={() => restore(restoring)}>
                Khôi phục
              </ui.Button>
            </>
          }
        >
          Máy tạo một phiên bản mới từ nội dung bản ngày {whenText(restoring.at)}; bản hiện tại vẫn nằm trong lịch sử. Nguồn
          được nạp lại.
        </ConfirmDialog>
      )}
    </div>
  );
}
