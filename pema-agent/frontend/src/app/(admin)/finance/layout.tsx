"use client";

// Tài chính & tiền thủ thuật (PB02). Old web: `prototype/finance/finance.js`, ONE page with four tabs, the month
// picker "Kỳ báo cáo" and "Làm mới" in the header, and a role/doctor picker in the top bar. Here every tab is a
// route (`/finance`, `/entries`, `/rates`, `/payments`) next to two screens the old web had no page for
// (`/periods`, the close of a month, and `/export`); the month is `?month=`; the projection comes from the signed-in
// session, there is no role picker: the owner alone flips between "Toàn phòng khám" and "Cá nhân" (`?scope=own`), a
// doctor only ever has the personal one. The tabs only list the pages; the BE refuses every call of a role without
// the permission.
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState, type ReactNode } from "react";

import { FinanceContext } from "@/components/finance/finance-context";
import { FinanceTabs } from "@/components/finance/finance-ui";
import { ListSkeleton, Notice, FilterChip, ChipRow } from "@/components/ops/ops-ui";
import {
  SCOPE_LABEL,
  isMonth,
  monthFromParam,
  scopeFor,
  type FinanceScope,
} from "@/lib/finance/finance-view";
import { useSession } from "@/lib/session/session-context";
import { Button } from "@/ui/button";
import { Field, FIELD_BASE_CLASS } from "@/ui/field";
import { PageHeading } from "@/ui/workspace";

const SCOPES: readonly FinanceScope[] = ["clinic", "own"];

function FinanceShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { user, can } = useSession();
  const [refreshKey, setRefreshKey] = useState(0);
  const canRead = can("finance.read");
  const canReadOwn = can("finance.read_own");
  const month = monthFromParam(params.get("month"));
  const scope = scopeFor({ canRead, canReadOwn }, params.get("scope"));
  const reload = useCallback(() => setRefreshKey((key) => key + 1), []);

  const value = useMemo(
    () => ({
      month,
      scope,
      canWrite: can("finance.write") && scope === "clinic",
      canClose: can("finance_period.close") && scope === "clinic",
      canCollect: can("finance.collect"),
      isOwner: user.role === "owner",
      refreshKey,
      reload,
    }),
    [month, scope, can, user.role, refreshKey, reload],
  );

  function go(nextMonth: string, nextScope: FinanceScope) {
    const next = new URLSearchParams(params.toString());
    next.set("month", nextMonth);
    if (nextScope === "own") next.set("scope", "own");
    else next.delete("scope");
    router.replace(`${pathname}?${next.toString()}`);
  }

  if (!canRead && !canReadOwn) {
    return (
      <div>
        <PageHeading title="Tài chính & tiền thủ thuật" />
        <Notice tone="warn">Vai trò của bạn không xem được dữ liệu tài chính.</Notice>
      </div>
    );
  }

  return (
    <FinanceContext.Provider value={value}>
      <div>
        <p className="text-eyebrow font-semibold tracking-wider text-ink-soft uppercase">
          ĐIỀU HÀNH • PEMA CLINIC
        </p>
        <PageHeading
          title="Tài chính & tiền thủ thuật"
          actions={
            <>
              {canRead && canReadOwn && (
                <ChipRow label="Phạm vi số liệu">
                  {SCOPES.map((option) => (
                    <FilterChip
                      key={option}
                      selected={scope === option}
                      onClick={() => go(month, option)}
                    >
                      {SCOPE_LABEL[option]}
                    </FilterChip>
                  ))}
                </ChipRow>
              )}
              <Field label="Kỳ báo cáo" className="mb-0">
                {(control) => (
                  <input
                    {...control}
                    type="month"
                    value={month}
                    onChange={(e) => {
                      if (isMonth(e.target.value)) go(e.target.value, scope);
                    }}
                    className={FIELD_BASE_CLASS}
                  />
                )}
              </Field>
              <Button variant="secondary" onClick={reload}>
                Làm mới
              </Button>
            </>
          }
        />
        <FinanceTabs pathname={pathname} month={month} scope={scope} />
        {children}
      </div>
    </FinanceContext.Provider>
  );
}

export default function FinanceLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ListSkeleton rows={3} />}>
      <FinanceShell>{children}</FinanceShell>
    </Suspense>
  );
}
