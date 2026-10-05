// ported from: web/src/pages/mcp-server-form-modal.tsx
"use client";

import { useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { ToggleKnob } from "@/components/admin/shared/ui-bits";
import { McpHeaderFields, type HeaderRow } from "@/components/admin/mcp/mcp-header-fields";

// Deviations: typed client; the contract names the display name `name`; header values go up only (the
// view says `has_headers`, never the values).
type McpServerListItem = Schemas["McpServerView"];

/**
 * Modal thêm/sửa 1 server MCP. `server=null` = tạo mới (mirror
 * `schedule-edit-drawer.tsx`: một component, một prop quyết định chế độ).
 *
 * KHÔNG có nút "Test kết nối" riêng (V1, xem plan phase-07): Lưu xong route
 * POST/PATCH tự nối lại NỀN (`ketNoiLaiServer` không chặn response) - trạng
 * thái hiện qua badge ở dòng server sau khi trang tự làm mới.
 */
export function McpServerFormModal({
  server,
  onClose,
  onSaved,
}: {
  server: McpServerListItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [ten, setTen] = useState(server?.name ?? "");
  const [url, setUrl] = useState(server?.url ?? "");
  const [enabled, setEnabled] = useState(server?.enabled ?? true);
  const [rows, setRows] = useState<HeaderRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const nen = useChotNen(onClose);

  const hopLe = Boolean(ten.trim() && url.trim());

  /** Rỗng (chưa gõ dòng nào hợp lệ) -> `undefined` = giữ header cũ khi sửa */
  function headersDeGui(): Record<string, string> | undefined {
    const entries = rows
      .map(({ key, value }) => [key.trim(), value] as const)
      .filter(([k, v]) => k && v);
    return entries.length ? Object.fromEntries(entries) : undefined;
  }

  async function luu() {
    if (!hopLe) return;
    setBusy(true);
    setError("");
    try {
      const headers = headersDeGui();
      if (server) {
        await unwrap(
          http.PATCH("/api/v1/admin/mcp/servers/{server_id}", {
            params: { path: { server_id: server.id } },
            body: { name: ten.trim(), url: url.trim(), enabled, headers },
          }),
        );
      } else {
        await unwrap(
          http.POST("/api/v1/admin/mcp/servers", {
            body: { name: ten.trim(), url: url.trim(), enabled, headers },
          }),
        );
      }
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function xoaHeaderDaLuu() {
    if (!server) return;
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/mcp/servers/{server_id}/headers", {
          params: { path: { server_id: server.id } },
        }),
      );
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]"
      {...nen}
    >
      <div className="flex max-h-[85dvh] w-full max-w-lg flex-col rounded-card bg-surface shadow-xl">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div className="font-semibold text-ink">
            {server ? `Sửa: ${server.name}` : "Thêm server MCP"}
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div>
            <label htmlFor="mcp-ten" className="mb-1.5 block text-small font-medium text-ink">
              Tên
            </label>
            <input
              id="mcp-ten"
              className="gc-input w-full"
              value={ten}
              onChange={(e) => setTen(e.target.value)}
              placeholder="vd: Notion"
              maxLength={200}
            />
          </div>

          <div>
            <label htmlFor="mcp-url" className="mb-1.5 block text-small font-medium text-ink">
              URL (Streamable HTTP)
            </label>
            <input
              id="mcp-url"
              className="gc-input w-full"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://mcp.example.com/mcp"
              maxLength={2048}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <div className="text-small font-medium text-ink">Bật server này</div>
              <div className="text-label text-ink-soft">
                Tắt thì bot không nối và không dùng được tool của nó
              </div>
            </div>
            <button
              type="button"
              aria-pressed={enabled}
              onClick={() => setEnabled((v) => !v)}
              className="shrink-0 cursor-pointer"
            >
              <ToggleKnob on={enabled} />
            </button>
          </div>

          <McpHeaderFields
            rows={rows}
            onChange={setRows}
            hasSavedHeaders={server?.has_headers ?? false}
            onRemoveSaved={() => void xoaHeaderDaLuu()}
            busy={busy}
          />

          {error && <p className="text-small text-danger">{error}</p>}
        </div>

        <div className="border-t border-line px-5 py-4">
          <button
            onClick={() => void luu()}
            disabled={busy || !hopLe}
            className="w-full cursor-pointer rounded-control bg-brand-500 py-2.5 text-body font-medium text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Đang lưu..." : server ? "Lưu thay đổi" : "Thêm server"}
          </button>
        </div>
      </div>
    </div>
  );
}
