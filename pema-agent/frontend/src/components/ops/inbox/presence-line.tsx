"use client";

// "Lan đang xem" / "Lan đang trả lời" beside a conversation. A warning only: nothing is locked, the person may
// still open the conversation and reply.
import type { PresenceViewer } from "@/lib/live/live-types";
import { presenceText, someoneReplying } from "@/lib/ops/presence-view";

export function PresenceLine({
  viewers,
  className = "",
}: {
  viewers: readonly PresenceViewer[];
  className?: string;
}) {
  const text = presenceText(viewers);
  if (!text) return null;
  const replying = someoneReplying(viewers);
  return (
    <span
      role="status"
      data-testid="presence-line"
      className={`inline-flex items-center gap-1.5 text-[12px] font-medium ${
        replying ? "text-amber-700 dark:text-amber-400" : "text-ink-soft"
      } ${className}`}
    >
      <span
        aria-hidden="true"
        className={`h-2 w-2 shrink-0 rounded-full ${replying ? "bg-amber-500" : "bg-brand-400"}`}
      />
      <span className="min-w-0 truncate">{text}</span>
    </span>
  );
}
