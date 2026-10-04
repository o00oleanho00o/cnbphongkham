// ported from: web/src/pages/schedule-page.tsx
"use client";

// Deviations: `accounts` from the shell context; the list is `GET /admin/schedules?account_id=` (no
// timezone in the response: each job carries its own `timezone`, the clinic zone is the default for new
// ones); thread names come from `GET /admin/threads`; update, delete and run address the job by id only.

import { useCallback, useEffect, useState } from "react";
import { useAdminAccounts } from "@/lib/admin/shared/accounts-context";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { CLINIC_TIME_ZONE } from "@/lib/ops/format";

type ScheduledJobItem = Schemas["ScheduledJob"];
import { PageHeader } from "@/components/admin/layout/page-header";
import { IconClock } from "@/components/admin/shared/dashboard-icons";
import { AccountFilter, accountLabel } from "@/components/admin/shared/account-filter";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { ScheduleEditDrawer } from "@/components/admin/schedules/schedule-edit-drawer";
import { ScheduleJobRow } from "@/components/admin/schedules/schedule-job-row";
import { ScheduleRunHistoryDrawer } from "@/components/admin/schedules/schedule-run-history-drawer";

/**
 * Trang Lịch hẹn: bot tự nhắn theo lịch (nhắc hẹn hoặc chạy 1 lượt agent).
 * Mọi mốc giờ hiển thị pin theo `timezone` server trả về (BOT_TIMEZONE),
 * không tự suy từ giờ trình duyệt - xem `shared/format-bot-time.ts`.
 */
export default function SchedulePage() {
  const { accounts } = useAdminAccounts();
  const [jobs, setJobs] = useState<ScheduledJobItem[]>([]);
  const timezone = CLINIC_TIME_ZONE;
  const [threadNames, setThreadNames] = useState<Map<string, string>>(new Map());
  const [accountFilter, setAccountFilter] = useState("");
  const [editing, setEditing] = useState<ScheduledJobItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [historyJob, setHistoryJob] = useState<ScheduledJobItem | null>(null);
  const [notice, setNotice] = useState<{ tone: "red" | "amber"; text: string } | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const reload = useCallback(async () => {
    const account_id = accountFilter || undefined;
    const [jobsRes, threadsRes] = await Promise.all([
      unwrap(http.GET("/api/v1/admin/schedules", { params: { query: { account_id } } })),
      unwrap(http.GET("/api/v1/admin/threads", { params: { query: { account_id, limit: 100 } } })),
    ]);
    setJobs(jobsRes);
    setThreadNames(
      new Map(
        threadsRes.map((t) => [`${t.account_id}:${t.thread_id}`, t.display_name || t.thread_id]),
      ),
    );
  }, [accountFilter]);

  useEffect(() => {
    reload().catch(() => setNotice({ tone: "red", text: "Không tải được danh sách lịch hẹn" }));
  }, [reload]);

  async function toggleEnabled(job: ScheduledJobItem) {
    setNotice(null);
    try {
      await unwrap(
        http.PATCH("/api/v1/admin/schedules/{job_id}", {
          params: { path: { job_id: job.id } },
          body: { enabled: !job.enabled },
        }),
      );
      await reload();
    } catch (err) {
      setNotice({ tone: "red", text: errorMessage(err) });
    }
  }

  async function remove(job: ScheduledJobItem) {
    const ok = await confirm({
      title: `Xóa lịch hẹn "${job.name}"?`,
      message: "Lịch sử chạy của lịch hẹn này cũng sẽ bị xóa theo, không khôi phục được.",
    });
    if (!ok) return;
    setNotice(null);
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/schedules/{job_id}", { params: { path: { job_id: job.id } } }),
      );
      await reload();
    } catch (err) {
      setNotice({ tone: "red", text: errorMessage(err) });
    }
  }

  async function runTrial(job: ScheduledJobItem) {
    const run = await unwrap(
      http.POST("/api/v1/admin/schedules/{job_id}/run", { params: { path: { job_id: job.id } } }),
    );
    await reload();
    return run;
  }

  return (
    <div>
      <PageHeader
        icon={IconClock}
        title="Lịch hẹn"
        subtitle="Bot tự nhắn theo lịch: nhắc hẹn hoặc chạy 1 lượt agent - xem, sửa, chạy thử ngay không cần chat"
        aside={
          <button
            onClick={() => setCreating(true)}
            className="rounded-lg bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-600"
          >
            Thêm lịch hẹn
          </button>
        }
      />

      {accounts.length > 1 && (
        <div className="mb-4 w-full sm:w-56">
          <AccountFilter accounts={accounts} value={accountFilter} onChange={setAccountFilter} />
        </div>
      )}

      {notice && (
        <p
          className={`mb-4 text-[13px] ${notice.tone === "red" ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400"}`}
        >
          {notice.text}
        </p>
      )}

      <div className="space-y-3">
        {jobs.length === 0 && (
          <div className="gc-card px-5 py-10 text-center text-ink-soft">
            Chưa có lịch hẹn nào - bấm "Thêm lịch hẹn" hoặc nhờ bot đặt lịch qua chat
          </div>
        )}
        {jobs.map((job) => (
          <ScheduleJobRow
            key={job.id}
            job={job}
            accountName={accounts.length > 1 ? accountLabel(accounts, job.account_id) : undefined}
            threadName={threadNames.get(`${job.account_id}:${job.thread_id}`) ?? job.thread_id}
            timezone={timezone}
            onToggle={() => toggleEnabled(job)}
            onRun={() => runTrial(job)}
            onEdit={() => setEditing(job)}
            onHistory={() => setHistoryJob(job)}
            onDelete={() => remove(job)}
          />
        ))}
      </div>

      {(editing || creating) && (
        <ScheduleEditDrawer
          job={editing}
          accounts={accounts}
          timezone={timezone}
          onClose={() => {
            setEditing(null);
            setCreating(false);
          }}
          onSaved={() => {
            setEditing(null);
            setCreating(false);
            void reload();
          }}
        />
      )}

      {historyJob && (
        <ScheduleRunHistoryDrawer
          job={historyJob}
          timezone={timezone}
          onClose={() => setHistoryJob(null)}
        />
      )}

      {confirmDialog}
    </div>
  );
}
