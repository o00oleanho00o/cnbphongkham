// Words and small calculations of the `/crm` screen (customer groups, contact log, automation rules). The wording is
// the one of the web prototype (prototype/shared/crm-automation.js `stageLabels`, crm-ui.js `summary` and
// `protocol`); the numbers themselves are computed by the backend (`GET /api/v1/crm/segments`).
import type { Schemas } from "@/lib/api";

type S = Schemas;

export type SegmentKey = S["CrmSegmentKey"];
export type SegmentPatient = S["CrmSegmentPatientOut"];
export type Activity = S["CrmActivityOut"];

export const SEGMENT_LABEL: Record<SegmentKey, string> = {
  new: "Khách mới",
  returning: "Khách quay lại",
  treating: "Đang điều trị",
  dormant: "Lâu chưa quay lại",
  reactivated: "Đã quay lại sau CSKH",
  at_risk: "Nguy cơ mất khách",
};

export const SEGMENT_HINT: Record<SegmentKey, string> = {
  new: "Chưa có buổi điều trị nào",
  returning: "Đã xong liệu trình, còn gần đây",
  treating: "Còn buổi chưa làm",
  dormant: "Từ 90 ngày chưa đến",
  reactivated: "Đến lại sau lần chăm sóc",
  at_risk: "Chưa có lịch mới, quá hạn hoặc bỏ dở",
};

/** Order of the cards: the five stages, then the cut that crosses them. */
export const SEGMENT_ORDER: readonly SegmentKey[] = [
  "new",
  "returning",
  "treating",
  "dormant",
  "reactivated",
  "at_risk",
];

export const SEND_MODE_LABEL: Record<S["RuleSendMode"], string> = {
  staff_task: "Chỉ tạo việc cho nhân viên",
  auto_reminder: "Nhắc lịch tự động",
  draft_for_review: "Soạn nháp, người duyệt rồi mới gửi",
};

export const ACTIVITY_KIND_LABEL: Record<string, string> = {
  cskh: "CSKH",
  complaint: "Khiếu nại",
};

export const activityKindLabel = (kind: string): string => ACTIVITY_KIND_LABEL[kind] ?? "CSKH";

/** "Quá hạn 14 ngày", "Dự kiến quay lại 20/09" or "Chưa có ngày dự kiến" (old `summary` card). */
export function expectedVisitText(
  row: Pick<SegmentPatient, "overdue_days" | "expected_next_visit_at">,
): string {
  if (row.overdue_days > 0) return `Quá hạn ${row.overdue_days} ngày`;
  if (row.expected_next_visit_at) return `Dự kiến ${formatDay(row.expected_next_visit_at)}`;
  return "Chưa có ngày dự kiến";
}

/** `2026-09-20` -> `20/09/2026`; anything else is shown as it came. */
export function formatDay(isoDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : isoDate;
}

const NO_PATIENTS: Record<SegmentKey, number> = {
  new: 0,
  returning: 0,
  treating: 0,
  dormant: 0,
  reactivated: 0,
  at_risk: 0,
};

/** Counts by key from the API answer; a group the answer lacks counts 0. */
export function countsOf(segments: readonly S["CrmSegmentCount"][]): Record<SegmentKey, number> {
  return segments.reduce((acc, s) => ({ ...acc, [s.key]: s.count }), NO_PATIENTS);
}

/** The group the screen opens on: the first non-empty stage, else the first card. */
export function defaultSegment(counts: Record<SegmentKey, number>): SegmentKey {
  return SEGMENT_ORDER.find((key) => counts[key] > 0) ?? "new";
}

export type ActivityFilter = {
  channel: "all" | S["CrmChannel"];
  outcome: "all" | S["CrmOutcome"];
};

/** Filter of the contact log (the page loads a page of it; the chips only narrow what is on screen). */
export function filterActivities(items: readonly Activity[], filter: ActivityFilter): Activity[] {
  return items.filter(
    (a) =>
      (filter.channel === "all" || a.channel === filter.channel) &&
      (filter.outcome === "all" || a.outcome === filter.outcome),
  );
}
