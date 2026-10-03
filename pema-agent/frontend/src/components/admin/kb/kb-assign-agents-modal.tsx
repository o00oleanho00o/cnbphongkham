// ported from: web/src/pages/kb-assign-agents-modal.tsx
"use client";

// Deviations: typed client and the contract's `IdList {ids}` for both calls.

import { useEffect, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { ToggleKnob } from "@/components/admin/shared/ui-bits";

type KbSourceListItem = Schemas["KbSource"];
type ManagedAgent = Schemas["AgentOut"];

/**
 * Gán MỘT nguồn cho nhiều agent, ngay tại trang Kho tri thức.
 *
 * Vì sao có modal này dù trang Agents đã gán được theo chiều kia: người vừa nạp
 * tài liệu nghĩ theo "tài liệu này cho ai đọc", không phải "agent này đọc được
 * những gì". Bắt họ nhớ tên nguồn rồi đi sang trang Agents tìm đúng agent chính
 * là ngõ cụt đã gặp thật - nguồn nạp xong nằm đó không agent nào đọc được,
 * trong khi bảng vẫn hiện "Sẵn sàng" nên mọi tín hiệu đều nói "xong rồi".
 *
 * Hai chiều cùng ghi `agent_kb_sources`, mỗi chiều THAY THẾ trọn danh sách theo
 * trục của nó - lưu ở đây đặt lại danh sách AGENT của nguồn này, không đụng
 * nguồn khác của cùng agent đó.
 */
export function KbAssignAgentsModal({
  source,
  onClose,
  onSaved,
}: {
  source: KbSourceListItem;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [agents, setAgents] = useState<ManagedAgent[] | null>(null);
  const [ticked, setTicked] = useState<Set<string> | null>(null);
  const [loi, setLoi] = useState("");
  const [dangLuu, setDangLuu] = useState(false);
  const nen = useChotNen(onClose);

  useEffect(() => {
    let huy = false;
    // Hai lời gọi song song: danh sách agent để hiện, và danh sách đang gán để
    // tick sẵn. Chờ cả hai rồi mới dựng `ticked` - dựng sớm từ một nửa dữ liệu
    // là ô tick nhấp nháy từ trạng thái sai sang trạng thái đúng.
    Promise.all([
      unwrap(http.GET("/api/v1/admin/agents")),
      unwrap(
        http.GET("/api/v1/admin/kb/sources/{source_id}/agents", {
          params: { path: { source_id: source.id } },
        }),
      ),
    ])
      .then(([ds, dangGan]) => {
        if (huy) return;
        setAgents(ds);
        setTicked(new Set(dangGan.ids));
      })
      .catch((err: unknown) => {
        if (huy) return;
        setAgents([]);
        setTicked(new Set());
        setLoi(errorMessage(err));
      });
    return () => {
      huy = true;
    };
  }, [source.id]);

  function toggle(id: string) {
    setTicked((truoc) => {
      if (!truoc) return truoc;
      const sau = new Set(truoc);
      if (sau.has(id)) sau.delete(id);
      else sau.add(id);
      return sau;
    });
  }

  async function luu() {
    if (!ticked) return;
    setDangLuu(true);
    setLoi("");
    try {
      await unwrap(
        http.PUT("/api/v1/admin/kb/sources/{source_id}/agents", {
          params: { path: { source_id: source.id } },
          body: { ids: [...ticked] },
        }),
      );
      onSaved();
      onClose();
    } catch (err: unknown) {
      setLoi(errorMessage(err));
    } finally {
      setDangLuu(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]"
      {...nen}
    >
      <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-card bg-surface shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="truncate font-semibold text-ink">Agent nào đọc được nguồn này</div>
            <div className="truncate text-label text-ink-soft">{source.name}</div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 cursor-pointer rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {agents === null && !loi && <p className="text-small text-ink-soft">Đang tải...</p>}
          {agents !== null && agents.length === 0 && !loi && (
            <p className="py-10 text-center text-small leading-relaxed text-ink-soft/60">
              Chưa có agent nào - tạo agent ở trang Agents trước, rồi quay lại gán nguồn
            </p>
          )}
          {agents !== null && agents.length > 0 && (
            <div className="divide-y divide-line">
              {agents.map((a) => (
                <div
                  key={a.id}
                  className="flex w-full items-center justify-between gap-4 py-3 first:pt-0"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 text-section">{a.icon}</span>
                    <span className="truncate text-body font-medium text-ink">{a.name}</span>
                  </div>
                  <button
                    type="button"
                    aria-label={`Bật tắt agent ${a.name}`}
                    aria-pressed={ticked?.has(a.id) ?? false}
                    onClick={() => toggle(a.id)}
                    className="shrink-0 cursor-pointer"
                  >
                    <ToggleKnob on={ticked?.has(a.id) ?? false} />
                  </button>
                </div>
              ))}
            </div>
          )}
          {loi && <p className="mt-3 text-small text-danger">{loi}</p>}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-3">
          {/* Nói thẳng hệ quả của việc bỏ tick hết: người dùng vừa mới lạc đúng
              vì "Sẵn sàng" nghe như đã dùng được. */}
          <span className="text-label text-ink-soft">
            {ticked && ticked.size === 0
              ? "Không agent nào đọc được nguồn này"
              : `${ticked?.size ?? 0} agent đọc được`}
          </span>
          <button
            onClick={() => void luu()}
            disabled={dangLuu || ticked === null}
            className="cursor-pointer rounded-control bg-brand-600 px-4 py-1.5 text-small font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {dangLuu ? "Đang lưu..." : "Lưu"}
          </button>
        </div>
      </div>
    </div>
  );
}
