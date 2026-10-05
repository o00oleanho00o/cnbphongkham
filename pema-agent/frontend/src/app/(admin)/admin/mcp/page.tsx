// ported from: web/src/pages/mcp-page.tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { IconGlobe } from "@/components/admin/shared/dashboard-icons";
import { EmptyRow, TableShell } from "@/components/admin/shared/ui-bits";
import { McpAssignAgentsModal } from "@/components/admin/mcp/mcp-assign-agents-modal";
import { McpServerFormModal } from "@/components/admin/mcp/mcp-server-form-modal";
import { McpServerRow } from "@/components/admin/mcp/mcp-server-row";

// Deviations: typed client over the contract's `McpServerView`; the page is a default export.
type McpServerListItem = Schemas["McpServerView"];

// Cùng lý do với `knowledge-page.tsx`: POST/PATCH nối lại server ở NỀN (không
// chặn response), nên trang phải tự làm mới định kỳ để thấy badge đổi
// cho_ket_noi -> da_ket_noi/loi mà không cần F5. Không phân trang/tìm kiếm
// (khác KB): số server MCP một cài đặt thực tế chỉ vài cái, thêm UI đó là
// over-engineer cho quy mô này.
const KHOANG_POLL_MS = 4000;

/**
 * Trang MCP: quản server MCP ngoài (HTTP-only) cho agent dùng tool của chúng.
 * Cùng dạng "danh sách + gán agent" với trang Kho tri thức - nạp xong PHẢI GÁN
 * cho agent thì bot mới gọi được tool (default-deny).
 */
export default function McpPage() {
  const [servers, setServers] = useState<McpServerListItem[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  // "new" = mở form ở chế độ tạo mới; một server cụ thể = chế độ sửa
  const [formFor, setFormFor] = useState<McpServerListItem | "new" | null>(null);
  const [ganAgentCho, setGanAgentCho] = useState<McpServerListItem | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  const reload = useCallback(() => {
    unwrap(http.GET("/api/v1/admin/mcp/servers"))
      .then((items) => {
        setServers(items);
        setLoadError("");
      })
      .catch((err: unknown) => {
        setServers((cu) => cu ?? []);
        setLoadError(errorMessage(err));
      });
  }, []);

  useEffect(() => {
    reload();
    const timer = window.setInterval(reload, KHOANG_POLL_MS);
    return () => window.clearInterval(timer);
  }, [reload]);

  async function remove(server: McpServerListItem) {
    const ok = await confirm({
      title: `Xóa server "${server.name}"?`,
      message:
        (server.bound_agent_count ?? 0) > 0
          ? `${server.bound_agent_count} agent đang dùng server này sẽ mất quyền gọi tool ngoài của nó.`
          : "Chưa agent nào dùng server này.",
    });
    if (!ok) return;
    setActionError("");
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/mcp/servers/{server_id}", {
          params: { path: { server_id: server.id } },
        }),
      );
      reload();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  async function reapprove(server: McpServerListItem) {
    setActionError("");
    try {
      await unwrap(
        http.POST("/api/v1/admin/mcp/servers/{server_id}/reapprove", {
          params: { path: { server_id: server.id } },
        }),
      );
      reload();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  return (
    <div>
      <PageHeader
        icon={IconGlobe}
        title="MCP"
        subtitle="Server MCP ngoài cắm cho agent dùng tool của chúng - thêm xong phải GÁN cho agent thì bot mới gọi được"
        aside={
          <button
            onClick={() => setFormFor("new")}
            className="cursor-pointer rounded-lg bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-600"
          >
            Thêm server
          </button>
        }
      />

      {actionError && (
        <p className="mb-4 text-[13px] text-red-600 dark:text-red-400">{actionError}</p>
      )}
      {loadError && <p className="mb-4 text-[13px] text-red-600 dark:text-red-400">{loadError}</p>}

      <TableShell
        headers={["Tên", "URL", "Trạng thái", "Số tool", "Agent đang dùng", "Cập nhật", ""]}
        minWidth={960}
        ghimCotCuoi
      >
        {servers === null ? (
          <EmptyRow colSpan={7} text="Đang tải..." />
        ) : servers.length === 0 ? (
          <EmptyRow
            colSpan={7}
            text='Chưa có server nào - bấm "Thêm server" để cắm MCP server ngoài'
          />
        ) : (
          servers.map((s) => (
            <McpServerRow
              key={s.id}
              server={s}
              onEdit={() => setFormFor(s)}
              onDelete={() => void remove(s)}
              onAssignAgents={() => setGanAgentCho(s)}
              onReapprove={() => void reapprove(s)}
            />
          ))
        )}
      </TableShell>

      {formFor && (
        <McpServerFormModal
          server={formFor === "new" ? null : formFor}
          onClose={() => setFormFor(null)}
          onSaved={() => {
            setFormFor(null);
            reload();
          }}
        />
      )}

      {ganAgentCho && (
        <McpAssignAgentsModal
          server={ganAgentCho}
          onClose={() => setGanAgentCho(null)}
          onSaved={reload}
        />
      )}

      {confirmDialog}
    </div>
  );
}
