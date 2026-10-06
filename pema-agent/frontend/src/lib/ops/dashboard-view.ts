// Pure helpers of the dashboard ("Tổng quan"). Behaviour source: prototype/shared/crm-ui.js `dashboard()`.
// The numbers come from `GET /api/v1/dashboard/kpis`; this file only words them. A rate the BE could not
// compute is `null` and shows as a dash, never as 0%.
import type { Schemas } from "@/lib/api";

export type DashboardRange = Schemas["DashboardRange"];

export const RANGES: readonly DashboardRange[] = ["today", "week", "month"];

export const RANGE_LABEL: Record<DashboardRange, string> = {
  today: "Hôm nay",
  week: "Tuần này",
  month: "Tháng này",
};

/** "47%" or "–" when there was nothing to divide by. */
export function percentLabel(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${value}%`;
}

/** "20/09/2026" for a day, "14/09 – 20/09/2026" for a span. */
export function spanLabel(from: string, to: string): string {
  const fmt = (d: string) => `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}`;
  return from === to ? fmt(from) : `${fmt(from).slice(0, 5)} – ${fmt(to)}`;
}

/** Share of `part` in `whole` as a CSS width, at least a sliver when there is something to show. */
export function barWidth(part: number, whole: number): string {
  if (whole <= 0 || part <= 0) return "0%";
  return `${Math.max(3, Math.round((part / whole) * 100))}%`;
}
