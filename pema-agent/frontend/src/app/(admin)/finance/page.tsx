"use client";

// Tổng quan (old web: `finance.js` `overview()`): the hero with the state of the month, the numbers, the
// contribution of every doctor and what waits for the accountant. Performed revenue and collected cash are
// different numbers and are shown apart. A doctor, and the owner on "Cá nhân", get the personal view: own revenue,
// own pending and approved fee, no cash and no debt (the BE sends none).
import Link from "next/link";
import { useCallback } from "react";

import { useFinance } from "@/components/finance/finance-context";
import { LoadState, StatusBadge } from "@/components/finance/finance-ui";
import { http, unwrap } from "@/lib/api/client";
import {
  MONTH_RULE,
  barPercent,
  financeHref,
  formatVnd,
  heroLine,
  heroOver,
  heroTitle,
  overviewTiles,
  type FinanceOverview,
} from "@/lib/finance/finance-view";
import { useLoad } from "@/lib/use-load";
import { buttonClass } from "@/ui/button";
import { Card } from "@/ui/card";
import { Tile } from "@/ui/tile";

function Hero({ data, isOwner }: { data: FinanceOverview; isOwner: boolean }) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-5 rounded-hero border border-brand-100 bg-brand-50 p-5 sm:p-6">
      <div className="min-w-0">
        <p className="text-eyebrow font-semibold tracking-wider text-brand-700">
          {heroOver(data.scope, isOwner)}
        </p>
        <h2 className="mt-1 text-subtitle font-bold text-heading">{heroTitle(data.scope)}</h2>
        <p className="mt-1 text-body text-ink-soft">{heroLine(data.month)}</p>
      </div>
      <StatusBadge status={data.period.status} />
    </section>
  );
}

function TeamBars({ data }: { data: FinanceOverview }) {
  return (
    <Card title={data.scope === "own" ? "Chi tiết của tôi" : "Đóng góp của đội ngũ"}>
      <ul className="divide-y divide-line">
        {data.team.map((doctor) => (
          <li
            key={doctor.doctor_id}
            className="flex flex-wrap items-center justify-between gap-3 py-3"
          >
            <div className="min-w-0 flex-1">
              <p className="text-body font-semibold text-ink">{doctor.doctor_name}</p>
              <p className="text-small text-ink-soft">
                {doctor.entry_count} lượt · Tiền thủ thuật {formatVnd(doctor.fee_vnd)}
              </p>
              <div
                className="mt-2 h-1.5 overflow-hidden rounded-pill bg-tile"
                role="img"
                aria-label={`${barPercent(doctor.revenue_vnd, data.summary.revenue_vnd)}% doanh số của kỳ`}
              >
                <i
                  className="block h-full rounded-pill bg-brand-400"
                  style={{ width: `${barPercent(doctor.revenue_vnd, data.summary.revenue_vnd)}%` }}
                />
              </div>
            </div>
            <strong className="text-body-lg text-heading tabular-nums">
              {formatVnd(doctor.revenue_vnd)}
            </strong>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Reconcile({ data, entriesHref }: { data: FinanceOverview; entriesHref: string }) {
  return (
    <Card title="Việc cần đối soát">
      <dl className="divide-y divide-line">
        <div className="flex items-center justify-between gap-3 py-2.5">
          <dt className="text-body text-ink">Lượt chờ kế toán duyệt</dt>
          <dd className="text-body-lg font-bold text-heading">{data.pending_entries}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 py-2.5">
          <dt className="text-body text-ink">Tiền chờ duyệt</dt>
          <dd className="text-body-lg font-bold text-heading tabular-nums">
            {formatVnd(data.summary.pending_vnd)}
          </dd>
        </div>
      </dl>
      <p className="mt-2 text-small text-ink-soft">{MONTH_RULE}</p>
      <Link href={entriesHref} className={buttonClass("secondary", "mt-4")}>
        Mở bảng tiền thủ thuật →
      </Link>
    </Card>
  );
}

export default function FinanceOverviewPage() {
  const { month, scope, isOwner, refreshKey } = useFinance();
  const load = useCallback(
    (signal: AbortSignal): Promise<FinanceOverview> => {
      void refreshKey; // "Làm mới" and every change raise it: a new load function means "fetch again"
      return unwrap(
        http.GET("/api/v1/finance/overview", { params: { query: { month, scope } }, signal }),
      );
    },
    [month, scope, refreshKey],
  );
  const { data, error, loading, reload } = useLoad(load);

  return (
    <div className="space-y-4">
      <LoadState error={error} loading={loading} hasData={data !== undefined} onRetry={reload} />
      {data && (
        <>
          <Hero data={data} isOwner={isOwner} />
          <div
            className={`grid grid-cols-2 gap-3.5 ${data.scope === "own" ? "xl:grid-cols-3" : "xl:grid-cols-4"}`}
          >
            {overviewTiles(data.summary, data.scope).map((tile) => (
              <Tile
                key={tile.label}
                label={tile.label}
                value={tile.value}
                note={tile.note}
                tone={tile.tone}
              />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <TeamBars data={data} />
            <Reconcile data={data} entriesHref={financeHref("/finance/entries", month, scope)} />
          </div>
        </>
      )}
    </div>
  );
}
