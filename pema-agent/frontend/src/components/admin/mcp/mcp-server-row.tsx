// ported from: web/src/pages/mcp-server-row.tsx
"use client";

import type { Schemas } from "@/lib/api";
import {
  IconPencil,
  IconUndo,
  IconUsers,
  IconWarning,
} from "@/components/admin/shared/dashboard-icons";
import { Badge, formatTime, O_GHIM_PHAI } from "@/components/admin/shared/ui-bits";
import { nhanTrangThai } from "@/lib/admin/mcp/mcp-status-label";

// Deviations: DTO is the contract's `McpServerView` (English fields). It carries `tools_snapshot` but no
// live `runtime`, so the tool count is the size of the approved snapshot.
type McpServerListItem = Schemas["McpServerView"];

/**
 * Quy đổi tone THUẦN ("ok"/"warn"/"muted") của `nhanTrangThai` sang tone của
 * `Badge` ("green"/"amber"/"gray") - giữ `mcp-status-label.ts` không phụ thuộc
 * UI để test được như hàm thuần.
 */
const BADGE_TONE = { ok: "green", warn: "amber", muted: "gray" } as const;

export function McpServerRow({
  server,
  onEdit,
  onDelete,
  onAssignAgents,
  onReapprove,
}: {
  server: McpServerListItem;
  onEdit: () => void;
  onDelete: () => void;
  /** Mở modal gán server này cho agent */
  onAssignAgents: () => void;
  /** Chỉ gọi được khi `trangThai === 'can_duyet_lai'` */
  onReapprove: () => void;
}) {
  const nhan = nhanTrangThai(server.status);
  const soTool = server.tools_snapshot?.length ?? 0;
  const tenTool = (server.tools_snapshot ?? []).map((t) => t.name).join(", ");

  return (
    <tr className="border-b border-line/60 last:border-0 hover:bg-tile/40">
      <td className="max-w-xs px-4 py-3 text-ink">
        <div className="truncate font-medium">{server.name}</div>
        {server.status === "loi" && server.error && (
          <div className="mt-0.5 truncate text-label text-danger" title={server.error}>
            {server.error}
          </div>
        )}
        {server.status === "can_duyet_lai" && (
          <div className="mt-0.5 text-label text-warning">
            Bộ tool của server đã đổi so với lần duyệt trước
          </div>
        )}
        {server.enabled === false && (
          <div className="mt-0.5 text-micro text-ink-soft">Đang tắt</div>
        )}
      </td>
      <td className="max-w-xs truncate px-4 py-3 text-ink-soft" title={server.url}>
        {server.url}
      </td>
      <td className="px-4 py-3">
        <Badge tone={BADGE_TONE[nhan.tone]}>{nhan.chu}</Badge>
      </td>
      <td className="px-4 py-3 text-ink-soft" title={tenTool || undefined}>
        {soTool}
      </td>
      {/* Cột duy nhất phân biệt "server đã nối" với "agent gọi được tool ngoài
          này" - server 0 agent thì bot vẫn không thấy tool nào của nó
          (default-deny), dù badge có hiện "Đã kết nối". */}
      <td className="px-4 py-3">
        <button
          onClick={onAssignAgents}
          title={
            (server.bound_agent_count ?? 0) === 0
              ? "Chưa agent nào dùng được - bấm để gán"
              : "Đổi agent dùng được server này"
          }
          className={`flex cursor-pointer items-center gap-1.5 text-small hover:underline ${
            (server.bound_agent_count ?? 0) === 0 ? "text-warning" : "text-ink-soft hover:text-ink"
          }`}
        >
          {(server.bound_agent_count ?? 0) === 0 ? (
            <>
              <IconWarning size={14} />
              Chưa gán
            </>
          ) : (
            <>
              <IconUsers size={14} />
              {server.bound_agent_count ?? 0} agent
            </>
          )}
        </button>
      </td>
      <td className="px-4 py-3 text-ink-soft">{formatTime(server.updated_at)}</td>
      <td className={`px-4 py-3 ${O_GHIM_PHAI}`}>
        <div className="flex items-center justify-end gap-3">
          {server.status === "can_duyet_lai" && (
            <button
              onClick={onReapprove}
              title="Xem bộ tool hiện tại là đúng ý, lấy làm mốc mới"
              className="flex cursor-pointer items-center gap-1 text-small text-warning hover:underline"
            >
              <IconUndo size={14} />
              Duyệt lại
            </button>
          )}
          <button
            onClick={onEdit}
            className="flex cursor-pointer items-center gap-1 text-small text-ink-soft hover:text-ink hover:underline"
          >
            <IconPencil size={14} />
            Sửa
          </button>
          <button
            onClick={onDelete}
            className="cursor-pointer text-small text-danger hover:underline"
          >
            Xóa
          </button>
        </div>
      </td>
    </tr>
  );
}
