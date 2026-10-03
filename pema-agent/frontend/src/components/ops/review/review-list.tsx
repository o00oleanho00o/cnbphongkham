"use client";

import { memo } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import { RiskBadge } from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { formatDateTime } from "@/lib/ops/format";
import { REVIEW_KIND_LABEL, REVIEW_STATUS_LABEL } from "@/lib/ops/labels";

type Item = Schemas["ReviewItemOut"];

type RowProps = {
  item: Item;
  patientName: string;
  selected: boolean;
  onOpen: (id: string) => void;
};

function previewOf(item: Item): string {
  if (item.draft_text) return item.draft_text;
  if (item.red_flags && item.red_flags.length > 0) return `Dấu hiệu: ${item.red_flags.join(", ")}`;
  return REVIEW_KIND_LABEL[item.kind];
}

function ReviewRowView({ item, patientName, selected, onOpen }: RowProps) {
  const doctorOnly = item.requires_doctor;
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(item.id)}
        aria-current={selected ? "true" : undefined}
        className={`w-full rounded-tile border px-3.5 py-3 text-left transition-colors ${
          selected ? "border-brand-500 bg-brand-50" : "border-line bg-surface hover:bg-tile/60"
        } ${item.risk_level === "red_flag" ? "border-l-4 border-l-danger" : ""}`}
      >
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-body font-semibold text-ink">{patientName}</span>
          <span className="shrink-0 text-micro text-ink-soft">
            {formatDateTime(item.created_at)}
          </span>
        </span>
        <span className="mt-0.5 line-clamp-2 block text-small text-ink-soft">
          {previewOf(item)}
        </span>
        <span className="mt-2 flex flex-wrap items-center gap-1.5">
          <Badge tone="blue" dot={false}>
            {REVIEW_KIND_LABEL[item.kind]}
          </Badge>
          <RiskBadge risk={item.risk_level} />
          {doctorOnly && (
            <Badge tone="red" dot={false}>
              Cần bác sĩ
            </Badge>
          )}
          {item.status !== "pending" && (
            <Badge tone="gray" dot={false}>
              {REVIEW_STATUS_LABEL[item.status]}
            </Badge>
          )}
          {item.kind === "reply_draft" && (item.sources?.length ?? 0) === 0 && (
            <Badge tone="amber" dot={false}>
              Không có nguồn
            </Badge>
          )}
        </span>
      </button>
    </li>
  );
}

const ReviewRow = memo(ReviewRowView);

export function ReviewList({
  items,
  selectedId,
  nameOf,
  onOpen,
}: {
  items: Item[];
  selectedId: string | null;
  nameOf: (item: Item) => string;
  onOpen: (id: string) => void;
}) {
  return (
    <ul className="space-y-2">
      {items.map((item) => (
        <ReviewRow
          key={item.id}
          item={item}
          patientName={nameOf(item)}
          selected={item.id === selectedId}
          onOpen={onOpen}
        />
      ))}
    </ul>
  );
}
