// ported from: web/src/pages/schedule-destination-fields.tsx
"use client";

// Deviations: threads come from `GET /admin/threads?account_id=` (`ThreadRow`, snake_case). New: when the
// chosen account runs the patient_channel profile the form says that only a message from an approved
// template may be sent on a schedule (an agent job may only draft); the BE enforces it (`policy_denied`).

import { useEffect, useState } from "react";
import type { AccountInfo } from "@/lib/admin/shared/account-info";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";

type ThreadItem = Schemas["ThreadRow"];
import { SelectMenu } from "@/components/admin/shared/select-menu";

const KIND_JOB_OPTIONS = [
  { value: "message", label: "Nhắn tin (không tốn lượt LLM)" },
  { value: "agent", label: "Chạy agent (có thể dùng tool)" },
];

/**
 * Ô chọn account + cuộc trò chuyện + loại job - CHỈ dùng lúc TẠO MỚI (job đã
 * tồn tại thì đích gửi + loại job đã ghim, không sửa được nữa - brief "sửa
 * được lịch và nội dung chứ không sửa được nơi gửi"). Tách khỏi
 * `schedule-edit-drawer.tsx` để file đó không vượt ngưỡng 200 dòng.
 */
export function ScheduleDestinationFields({
  accounts,
  accountId,
  threadId,
  kind,
  onChange,
}: {
  accounts: AccountInfo[];
  accountId: string;
  threadId: string;
  kind: string;
  onChange: (patch: {
    accountId?: string;
    threadId?: string;
    threadType?: number;
    kind?: "message" | "agent";
  }) => void;
}) {
  const [threads, setThreads] = useState<ThreadItem[]>([]);

  useEffect(() => {
    if (!accountId) return;
    unwrap(
      http.GET("/api/v1/admin/threads", {
        params: { query: { account_id: accountId, limit: 100 } },
      }),
    )
      .then(setThreads)
      .catch(() => setThreads([]));
  }, [accountId]);

  const threadOptions = threads.map((t) => ({
    value: t.thread_id,
    label: t.display_name || t.thread_id,
  }));

  return (
    <>
      <div>
        <label htmlFor="sch-account" className="mb-1.5 block text-[13px] font-medium text-ink">
          Account
        </label>
        <SelectMenu
          id="sch-account"
          value={accountId}
          options={accounts.map((a) => ({ value: a.id, label: a.label }))}
          onChange={(v) => onChange({ accountId: v, threadId: "" })}
        />
      </div>
      <div>
        <label htmlFor="sch-thread" className="mb-1.5 block text-[13px] font-medium text-ink">
          Cuộc trò chuyện{" "}
          <span className="font-normal text-ink-soft">(đích gửi, không đổi được sau khi tạo)</span>
        </label>
        {threadOptions.length === 0 ? (
          <p className="text-[12px] leading-[1.6] text-ink-soft">
            Account này chưa có cuộc trò chuyện nào ghi nhận - phải có ít nhất 1 tin đến trước.
          </p>
        ) : (
          <SelectMenu
            id="sch-thread"
            value={threadId}
            options={threadOptions}
            onChange={(v) =>
              onChange({
                threadId: v,
                threadType: threads.find((t) => t.thread_id === v)?.thread_type ?? 0,
              })
            }
          />
        )}
      </div>
      {accounts.find((a) => a.id === accountId)?.policy_profile === "patient_channel" && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] leading-[1.6] text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200">
          Tài khoản này dùng hồ sơ Kênh bệnh nhân: lịch chỉ được gửi tin từ mẫu đã được bác sĩ duyệt
          (loại Nhắn tin). Job chạy agent chỉ soạn nháp để người duyệt, không tự gửi.
        </p>
      )}
      <div>
        <label htmlFor="sch-kind" className="mb-1.5 block text-[13px] font-medium text-ink">
          Loại job
        </label>
        <SelectMenu
          id="sch-kind"
          value={kind}
          options={KIND_JOB_OPTIONS}
          onChange={(v) => onChange({ kind: v as "message" | "agent" })}
        />
      </div>
    </>
  );
}
