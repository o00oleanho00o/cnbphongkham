"use client";

// New in Pema (no zalo-agent original): the audit log, an append-only record of who did what (sign-ins,
// approvals, kill switch, policy changes...). `GET /admin/logs/audit` with its filters (action, entity
// type, date range) and offset paging. Read only; the BE writes it, nothing here can change it.
import { useCallback, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import {
  Badge,
  EmptyRow,
  ListToolbar,
  TableShell,
  formatTime,
} from "@/components/admin/shared/ui-bits";
import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { ROLE_LABEL } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

const PAGE_SIZE = 50;

const ENTITY_OPTIONS: SelectOption[] = [
  { value: "", label: "Mọi đối tượng" },
  { value: "patient", label: "Bệnh nhân" },
  { value: "appointment", label: "Lịch hẹn" },
  { value: "crm_task", label: "Việc chăm sóc" },
  { value: "review_item", label: "Mục duyệt AI" },
  { value: "message_template", label: "Tin nhắn mẫu" },
  { value: "channel_setting", label: "Công tắc kênh" },
  { value: "account", label: "Tài khoản Zalo" },
];

export function AuditLogTable() {
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [page, setPage] = useState(0);

  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/admin/logs/audit", {
          params: {
            query: {
              action: action.trim() || undefined,
              entity_type: entity || undefined,
              limit: PAGE_SIZE,
              offset: page * PAGE_SIZE,
            },
          },
          signal,
        }),
      ),
    [action, entity, page],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = data?.items ?? [];
  const hasMore = data ? (page + 1) * PAGE_SIZE < data.total : false;

  return (
    <div>
      <ListToolbar
        query={action}
        onQuery={(value) => {
          setAction(value);
          setPage(0);
        }}
        placeholder="Lọc theo hành động, ví dụ review.approve"
        filter={
          <SelectMenu
            size="md"
            ariaLabel="Lọc theo đối tượng"
            value={entity}
            options={ENTITY_OPTIONS}
            onChange={(value) => {
              setEntity(value);
              setPage(0);
            }}
          />
        }
        page={page}
        hasMore={hasMore}
        onPage={setPage}
      />

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={4} />}

      <TableShell
        headers={["Lúc", "Người thực hiện", "Hành động", "Đối tượng", "Chi tiết"]}
        minWidth={860}
      >
        {data && items.length === 0 && <EmptyRow colSpan={5} text="Không có bản ghi nào khớp" />}
        {items.map((row) => (
          <tr key={row.id} className="border-b border-line/60 last:border-0 hover:bg-tile/40">
            <td className="px-4 py-3 whitespace-nowrap text-ink-soft">
              {formatTime(row.occurred_at)}
            </td>
            <td className="px-4 py-3">
              <Badge tone={row.actor_type === "user" ? "blue" : "gray"} dot={false}>
                {row.actor_type === "user" && row.actor_role
                  ? ROLE_LABEL[row.actor_role]
                  : row.actor_type}
              </Badge>
            </td>
            <td className="px-4 py-3 font-mono text-label text-ink">{row.action}</td>
            <td className="px-4 py-3 text-ink-soft">
              {row.entity_type}
              {row.entity_id ? (
                <span className="text-ink-soft/60"> · {row.entity_id.slice(0, 8)}</span>
              ) : null}
            </td>
            <td className="max-w-xs truncate px-4 py-3 text-label text-ink-soft">
              {row.details ? JSON.stringify(row.details) : "-"}
            </td>
          </tr>
        ))}
      </TableShell>
      <p className="mt-3 text-label text-ink-soft">
        Nhật ký chỉ thêm, không sửa hay xóa được. Nội dung tin nhắn của bệnh nhân không được ghi ở
        đây.
      </p>
    </div>
  );
}
