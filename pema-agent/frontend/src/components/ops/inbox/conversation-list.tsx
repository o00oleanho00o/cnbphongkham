"use client";

import { memo } from "react";

import { Badge, InitialAvatar } from "@/components/admin/shared/ui-bits";
import { Badge as KitBadge } from "@/ui/badge";
import { PresenceLine } from "@/components/ops/inbox/presence-line";
import type { Schemas } from "@/lib/api";
import { viewersOf } from "@/lib/live/live-types";
import { formatDateTime } from "@/lib/ops/format";
import { holderText, overLine } from "@/lib/ops/inbox-view";
import { CHANNEL_KIND_LABEL, CONVERSATION_STATUS_LABEL } from "@/lib/ops/labels";

type Summary = Schemas["ConversationSummary"];
type Identity = Schemas["IdentityOut"];
type Tone = "blue" | "gray" | "green" | "red" | "amber";

const STATUS_TONE: Record<Schemas["ConversationStatus"], Tone> = {
  open: "green",
  pending_review: "amber",
  handoff: "red",
  closed: "gray",
};

export function conversationTitle(
  c: Pick<Summary, "patient_display_name" | "patient_code">,
): string {
  return c.patient_display_name ?? c.patient_code ?? "Khách chưa gắn hồ sơ";
}

type RowProps = {
  conversation: Summary;
  selected: boolean;
  onOpen: (id: string) => void;
  meId: string;
  identities: readonly Identity[];
};

function ConversationRowView({ conversation: c, selected, onOpen, meId, identities }: RowProps) {
  const title = conversationTitle(c);
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(c.id)}
        aria-current={selected ? "true" : undefined}
        className={`flex min-h-[72px] w-full items-start gap-3 rounded-tile border px-3 py-3 text-left transition-colors ${
          selected ? "border-brand-500 bg-brand-50" : "border-line bg-surface hover:bg-tile/60"
        }`}
      >
        <InitialAvatar name={title} />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-eyebrow font-semibold tracking-wide text-ink-soft uppercase">
            {overLine(c, identities)}
          </span>
          <span className="block truncate text-body font-semibold text-ink">{title}</span>
          <span className="mt-0.5 line-clamp-2 block text-small text-ink-soft">
            {c.last_message_preview ?? "Chưa có tin nhắn"}
          </span>
          <span className="mt-0.5 block text-label text-ink-soft">
            {holderText(c, meId)} · {formatDateTime(c.last_message_at)}
          </span>
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <Badge tone={STATUS_TONE[c.status]} dot={false}>
              {CONVERSATION_STATUS_LABEL[c.status]}
            </Badge>
            {c.has_pending_review && (
              <Badge tone="amber" dot={false}>
                Có nháp chờ duyệt
              </Badge>
            )}
            <span className="text-micro text-ink-soft">{CHANNEL_KIND_LABEL[c.channel]}</span>
          </span>
          <PresenceLine viewers={viewersOf(c)} className="mt-1 max-w-full" />
        </span>
        {(c.unread_count ?? 0) > 0 && (
          <span className="mt-4 shrink-0">
            <KitBadge tone="brand" dot={false}>
              {c.unread_count} tin chưa đọc
            </KitBadge>
          </span>
        )}
      </button>
    </li>
  );
}

const ConversationRow = memo(ConversationRowView);

export function ConversationList({
  items,
  selectedId,
  onOpen,
  meId,
  identities = [],
}: {
  items: Summary[];
  selectedId: string | null;
  onOpen: (id: string) => void;
  /** The signed-in operator, to say "Bạn đang giữ". */
  meId: string;
  /** The clinic identities, to name the one a thread runs on. */
  identities?: readonly Identity[];
}) {
  return (
    <ul className="space-y-2">
      {items.map((c) => (
        <ConversationRow
          key={c.id}
          conversation={c}
          selected={c.id === selectedId}
          onOpen={onOpen}
          meId={meId}
          identities={identities}
        />
      ))}
    </ul>
  );
}
