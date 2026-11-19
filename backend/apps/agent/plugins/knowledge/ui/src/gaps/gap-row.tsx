/** One question with no document: the question, how often and where it was asked, and what can be done with it. */
import { formatDate } from "../logic";
import { ui } from "../sdk";
import type { Gap } from "../types";
import { countText, relativeTime } from "./gaps-logic";

export function GapRow({
  gap,
  busy,
  onWrite,
  onIgnore,
  onReopen,
}: {
  gap: Gap;
  busy: boolean;
  onWrite: () => void;
  onIgnore: () => void;
  onReopen: () => void;
}) {
  const open = gap.state === "open";
  return (
    <li className="flex flex-col gap-3 rounded-tile border border-line bg-surface px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-body font-bold break-words text-heading">{gap.question}</p>
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-label text-ink-soft">
          <ui.Badge tone={gap.count >= 5 ? "warning" : "neutral"}>{countText(gap.count)}</ui.Badge>
          <span>Kênh {gap.channel}</span>
          <span>
            Gần nhất {relativeTime(gap.last_asked_at)} ({formatDate(gap.last_asked_at)})
          </span>
        </p>
      </div>
      <div className="flex flex-wrap gap-2 max-sm:[&>button]:flex-1">
        {open && (
          <ui.Button disabled={busy} onClick={onWrite}>
            Viết câu trả lời
          </ui.Button>
        )}
        {open && (
          <ui.Button variant="secondary" disabled={busy} onClick={onIgnore}>
            Bỏ qua
          </ui.Button>
        )}
        {!open && (
          <ui.Button variant="secondary" disabled={busy} onClick={onReopen}>
            Mở lại
          </ui.Button>
        )}
      </div>
    </li>
  );
}
