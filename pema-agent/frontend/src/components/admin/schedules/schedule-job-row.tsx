// ported from: web/src/pages/schedule-job-row.tsx
"use client";

import { useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";

type ScheduledJobItem = Schemas["ScheduledJob"];
type ScheduledJobRunItem = Schemas["JobRunRecord"];
import { formatBotTime } from "@/lib/admin/shared/format-bot-time";
import { Badge } from "@/components/admin/shared/ui-bits";

/** Nhãn kiểu lịch đọc được, không phải mã kỹ thuật */
/** Where the job came from (new: the contract records it; a CRM rule job is a care task, not a chat reminder) */
const ORIGIN_LABEL: Record<NonNullable<ScheduledJobItem["origin"]>, string> = {
  agent_tool: "Do trợ lý AI đặt",
  staff: "Nhân viên đặt",
  crm_rule: "Quy tắc chăm sóc",
  system: "Hệ thống",
};

function scheduleLabel(job: ScheduledJobItem): string {
  if (job.schedule_kind === "once") return "Một lần";
  if (job.schedule_kind === "every") return `Mỗi ${job.every_minutes} phút`;
  return `Cron: ${job.cron_expr}`;
}

/**
 * Badge trạng thái lần chạy cuối. `blocked` (job bị chặn ở preflight - account
 * rớt phiên, bot tắt cho thread) là đường DUY NHẤT người dùng biết job đang
 * hỏng vì job lỗi cố ý không nhắn gì - PHẢI hiện rõ, không phải trang trí.
 */
function statusBadge(status: string | null): {
  tone: "blue" | "gray" | "green" | "red" | "amber";
  text: string;
} {
  switch (status) {
    case "ok":
      return { tone: "green", text: "Thành công" };
    case "silent":
      return { tone: "blue", text: "Im lặng (agent chọn không báo)" };
    case "skipped":
      return { tone: "amber", text: "Bị bỏ lượt" };
    case "error":
      return { tone: "red", text: "Lỗi" };
    case "interrupted":
      return { tone: "amber", text: "Bị ngắt giữa chừng" };
    case "blocked":
      return { tone: "red", text: "Đang bị chặn" };
    default:
      return { tone: "gray", text: "Chưa chạy lần nào" };
  }
}

export function ScheduleJobRow({
  job,
  accountName,
  threadName,
  timezone,
  onToggle,
  onRun,
  onEdit,
  onHistory,
  onDelete,
}: {
  job: ScheduledJobItem;
  accountName?: string;
  threadName: string;
  timezone: string;
  onToggle: () => void;
  onRun: () => Promise<ScheduledJobRunItem | null>;
  onEdit: () => void;
  onHistory: () => void;
  onDelete: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<string | null>(null);
  const status = statusBadge(job.last_status ?? null);
  const canShowError =
    (job.last_status === "error" || job.last_status === "blocked") && job.last_error;

  // Job chạy đủ suất thì `markRun` TỰ đặt enabled=0 + next_run_at=NULL
  // (scheduled-job-store.ts) - không phải người dùng tắt. Trước đây cả hai ca
  // cùng hiện "Đã tắt", đọc lên như thể ai đó vừa tắt một lịch còn hiệu lực.
  const finished =
    !job.enabled &&
    job.next_run_at == null &&
    job.max_runs != null &&
    job.run_count >= job.max_runs;

  // Bật lại job không còn mốc chạy kế là một công tắc RỖNG: `listDueJobs` lọc
  // `next_run_at IS NOT NULL` nên không tick nào thấy job đó nữa. Chặn ngay ở
  // nút thay vì để người dùng bật rồi ngồi đợi một lượt không bao giờ tới.
  const toggleDisabled = !job.enabled && job.next_run_at == null;

  async function handleRun() {
    setRunning(true);
    setRunResult(null);
    try {
      const run = await onRun();
      setRunResult(
        run
          ? `Kết quả chạy thử: ${run.status} - ${run.detail || "(không có mô tả)"}`
          : "Không ghi nhận được kết quả",
      );
    } catch (err) {
      setRunResult(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    // KHÔNG đè `bg-tile/30` lên `.gc-card` như trước: lớp xám mờ đó cộng với
    // nền trắng 95% của card làm cả thẻ chìm hẳn vào ảnh nền, đọc rất mệt.
    // Để card giữ đúng nền của design system, giống hệt trang Cấu hình.
    <div className="gc-card space-y-2.5 rounded-2xl px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[15px] font-semibold text-ink">{job.name}</span>
        <Badge tone={job.kind === "agent" ? "blue" : "gray"} dot={false}>
          {job.kind === "agent" ? "Agent" : "Nhắn tin"}
        </Badge>
        {job.origin && (
          <Badge tone="gray" dot={false}>
            {ORIGIN_LABEL[job.origin]}
          </Badge>
        )}
        <Badge tone="gray" dot={false}>
          {scheduleLabel(job)}
        </Badge>
        <Badge tone={status.tone}>{status.text}</Badge>
        {!job.enabled &&
          (finished ? (
            <Badge tone="gray" dot={false}>
              Đã xong (chạy đủ {job.max_runs} lần)
            </Badge>
          ) : (
            <Badge tone="gray" dot={false}>
              Đã tắt
            </Badge>
          ))}
      </div>

      <div className="text-[13px] leading-[1.6] text-ink-soft">
        {accountName && <>{accountName} · </>}
        {threadName} · Lần kế tiếp:{" "}
        {job.enabled
          ? formatBotTime(job.next_run_at, timezone)
          : finished
            ? "không còn lần nào"
            : "-"}
        {job.last_run_at && <> · Chạy gần nhất: {formatBotTime(job.last_run_at, timezone)}</>}
      </div>

      {canShowError && (
        <div className="rounded-lg border border-red-100 bg-red-50 px-3 py-2 text-[12px] leading-[1.6] text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300">
          {job.last_error}
        </div>
      )}

      {runResult && (
        <div className="rounded-lg border border-line bg-surface px-3 py-2 text-[12px] leading-[1.6] text-ink-soft">
          {runResult}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          onClick={onToggle}
          disabled={toggleDisabled}
          className={`relative h-5 w-9 rounded-full transition-colors ${job.enabled ? "bg-brand-500" : "bg-slate-300 dark:bg-slate-600"} ${toggleDisabled ? "cursor-not-allowed opacity-50" : ""}`}
          title={
            toggleDisabled
              ? "Lịch này không còn mốc chạy nào - bật lại cũng không chạy nữa. Bấm Sửa để đặt lịch mới."
              : job.enabled
                ? "Đang bật - bấm để tắt"
                : "Đang tắt - bấm để bật"
          }
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all ${job.enabled ? "left-[18px]" : "left-0.5"}`}
          />
        </button>
        <button
          onClick={handleRun}
          disabled={running}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-brand-600 hover:bg-brand-50 disabled:opacity-50"
        >
          {running ? "Đang chạy..." : "Chạy thử ngay"}
        </button>
        <button
          onClick={onHistory}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink hover:bg-tile"
        >
          Lịch sử
        </button>
        <button
          onClick={onEdit}
          className="rounded-lg border border-line bg-surface px-3 py-1.5 text-[13px] font-medium text-ink hover:bg-tile"
        >
          Sửa
        </button>
        <button
          onClick={onDelete}
          className="rounded-lg px-3 py-1.5 text-[13px] text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40"
        >
          Xóa
        </button>
      </div>
    </div>
  );
}
