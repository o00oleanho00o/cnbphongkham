"use client";

// Lịch trực (frames WM30-WM41): who covers which identity, when. One tab per customer identity, the people on
// duty now (with "Kết thúc ca" for owner and manager), and a week with every shift as a block. Shifts repeat by
// weekday or fall on one day; an end before the start means the next morning. New conversations and the end of a
// shift are routed by this roster (the BE does it). Owner and manager add, edit and delete shifts; the other
// operators read only (`roster.read`).
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { InitialAvatar } from "@/components/admin/shared/ui-bits";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { RosterDialog } from "@/components/ops/roster/roster-dialog";
import { WeekGrid } from "@/components/ops/roster/week-grid";
import { EmptyState, ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useIdentities } from "@/lib/identities/use-identities";
import { clinicDateKey } from "@/lib/ops/format";
import {
  addDays,
  emptyForm,
  endShiftText,
  entriesOn,
  formOfEntry,
  momentTitle,
  mondayOf,
  onDutyLine,
  weekTitle,
  type RosterForm,
} from "@/lib/ops/roster-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Tabs } from "@/ui/tabs";

type Entry = Schemas["RosterEntryOut"];

type DialogState = { form: RosterForm; entry: Entry | null } | null;

const READ_ONLY_TEXT =
  "Bạn chỉ xem được lịch trực. Thêm, sửa ca và kết thúc ca là việc của chủ phòng khám và quản lý.";

function clinicClock(): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date());
  return parts.replace("24:", "00:");
}

function RosterContent() {
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const { can } = useSession();
  const canManage = can("roster.manage");
  const canEndShift = can("thread.end_shift");
  const {
    identities,
    loading: identitiesLoading,
    error: identitiesError,
    reload: reloadIdentities,
  } = useIdentities();
  const customer = useMemo(() => identities.filter((i) => i.purpose === "customer"), [identities]);
  const wanted = params.get("identity");
  const current = customer.find((i) => i.id === wanted) ?? customer[0] ?? null;
  const accountId = current?.id ?? null;

  const today = clinicDateKey();
  const [monday, setMonday] = useState(() => mondayOf(today));
  const [dialog, setDialog] = useState<DialogState>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const loadRoster = useCallback(
    async (signal: AbortSignal): Promise<Entry[]> => {
      if (!accountId) return [];
      return unwrap(
        http.GET("/api/v1/roster", { params: { query: { account_id: accountId } }, signal }),
      );
    },
    [accountId],
  );
  const roster = useLoad(loadRoster);
  const loadDuty = useCallback(
    async (signal: AbortSignal) => {
      if (!accountId) return null;
      return unwrap(
        http.GET("/api/v1/identities/{account_id}/on-duty", {
          params: { path: { account_id: accountId } },
          signal,
        }),
      );
    },
    [accountId],
  );
  const duty = useLoad(loadDuty);
  const entries = roster.data ?? [];

  const selectIdentity = useCallback(
    (id: string) => router.replace(`/admin/roster?identity=${encodeURIComponent(id)}`),
    [router],
  );

  const reloadAll = useCallback(() => {
    roster.reload();
    duty.reload();
  }, [roster, duty]);

  const openAdd = useCallback(
    (weekday: RosterForm["weekdays"][number] | null) => {
      if (!accountId) return;
      setDialog({ form: emptyForm(accountId, "", weekday), entry: null });
    },
    [accountId],
  );

  async function removeEntry(entry: Entry) {
    const ok = await confirm({
      title: "Xóa ca trực này?",
      message: `${entry.user_name} sẽ không còn được xếp trực "${current?.label ?? ""}" vào các giờ này. Hội thoại đang giữ không bị đổi.`,
      confirmLabel: "Xóa ca",
    });
    if (!ok) return;
    try {
      await unwrap(
        http.DELETE("/api/v1/roster/{entry_id}", { params: { path: { entry_id: entry.id } } }),
      );
      toast.push("success", "Đã xóa ca trực.");
      setDialog(null);
      reloadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
  }

  async function endShift(operator: { id: string; name: string }) {
    const ok = await confirm({
      title: `Kết thúc ca của ${operator.name}?`,
      message:
        "Các hội thoại đang mở của " +
        `${operator.name} chuyển cho người đang trực danh tính đó; nếu không có ai trực, chuyển về hàng chờ. Cả hai bên và nhóm Zalo nhận thông báo.`,
      confirmLabel: "Kết thúc ca",
    });
    if (!ok) return;
    try {
      const result = await unwrap(
        http.POST("/api/v1/staff/{user_id}/end-shift", {
          params: { path: { user_id: operator.id } },
        }),
      );
      toast.push("success", endShiftText(result));
      reloadAll();
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
  }

  const header = (
    <PageHeader
      title="Lịch trực"
      subtitle="Ai trực danh tính nào, khi nào. Hội thoại mới và khi hết ca được giao theo lịch này."
      aside={
        canManage && accountId ? (
          <Button onClick={() => openAdd(null)}>
            <span aria-hidden>+</span> Thêm ca trực
          </Button>
        ) : undefined
      }
    />
  );

  if (identitiesLoading && identities.length === 0) {
    return (
      <div>
        {header}
        <ListSkeleton rows={3} />
      </div>
    );
  }
  if (identitiesError && identities.length === 0) {
    return (
      <div>
        {header}
        <RetryNotice message="Không tải được lịch trực." onRetry={reloadIdentities} />
      </div>
    );
  }
  if (!current) {
    return (
      <div>
        {header}
        <EmptyState
          title="Chưa có danh tính khách hàng nào"
          hint="Thêm tài khoản Zalo ở trang Tài khoản Zalo rồi quay lại để xếp lịch trực."
        />
      </div>
    );
  }

  const onDuty = duty.data?.operators ?? [];
  const dutyEntry = (id: string) =>
    entriesOn(entries, today).find((e) => e.user_id === id && e.start <= clinicClock()) ?? null;

  return (
    <div>
      {header}
      {!canManage && (
        <div className="mb-4">
          <Notice tone="info">{READ_ONLY_TEXT}</Notice>
        </div>
      )}
      <Tabs
        label="Danh tính"
        idPrefix="roster"
        items={customer.map((i) => ({ id: i.id, label: i.label }))}
        value={current.id}
        onChange={selectIdentity}
        segmented
      />

      <div className="space-y-4">
        <Card
          title="Đang trực bây giờ"
          subtitle={`${current.label} · ${momentTitle(today, clinicClock())}`}
        >
          {duty.error && !duty.data && <RetryNotice message={duty.error} onRetry={duty.reload} />}
          {duty.data && onDuty.length === 0 && (
            <p className="text-body text-ink-soft">
              Chưa ai trực danh tính này. Hội thoại mới vào hàng chờ và ai cũng nhận được.
            </p>
          )}
          {onDuty.length > 0 && (
            <ul className="divide-y divide-line rounded-tile border border-line">
              {onDuty.map((operator) => (
                <li key={operator.id} className="flex items-center gap-3 px-3 py-2.5">
                  <InitialAvatar name={operator.name} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-body font-semibold text-ink">{operator.name}</p>
                    <p className="text-label text-ink-soft">
                      {onDutyLine(operator.role, dutyEntry(operator.id))}
                    </p>
                  </div>
                  {canEndShift && (
                    <Button variant="secondary" onClick={() => void endShift(operator)}>
                      Kết thúc ca
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        {roster.error && !roster.data && (
          <RetryNotice message="Không tải được lịch trực." onRetry={roster.reload} />
        )}
        {roster.loading && !roster.data && <ListSkeleton rows={3} />}
        {roster.data && entries.length === 0 && (
          <EmptyState
            title="Chưa có ca trực nào"
            hint="Chưa ai trực danh tính này. Hội thoại mới vào hàng chờ và ai cũng nhận được."
            action={
              canManage ? <Button onClick={() => openAdd(null)}>Thêm ca trực</Button> : undefined
            }
          />
        )}
        {roster.data && entries.length > 0 && (
          <Card
            title={weekTitle(monday)}
            subtitle="Mỗi khối là một ca trực của một người; ca lặp theo thứ hiện ở mọi tuần."
            aside={
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => setMonday(addDays(monday, -7))}>
                  Tuần trước
                </Button>
                <Button variant="secondary" onClick={() => setMonday(addDays(monday, 7))}>
                  Tuần sau
                </Button>
              </div>
            }
          >
            <WeekGrid
              monday={monday}
              today={today}
              entries={entries}
              canManage={canManage}
              onAdd={openAdd}
              onEdit={(entry) => setDialog({ form: formOfEntry(entry), entry })}
            />
          </Card>
        )}
      </div>

      {dialog && (
        <RosterDialog
          key={dialog.entry?.id ?? "new"}
          initial={dialog.form}
          entry={dialog.entry}
          identities={customer}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            reloadAll();
          }}
          onDelete={(entry) => void removeEntry(entry)}
        />
      )}
      {confirmDialog}
    </div>
  );
}

export default function RosterPage() {
  return (
    <Suspense fallback={<ListSkeleton rows={3} />}>
      <RosterContent />
    </Suspense>
  );
}
