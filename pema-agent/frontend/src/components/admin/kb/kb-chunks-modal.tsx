// ported from: web/src/pages/kb-chunks-modal.tsx
"use client";

// Deviations: `GET .../chunks` takes offset/limit but returns a bare array (no total), so one extra row is
// asked for to know whether a next page exists and the total comes from `source.chunk_count`; `KbChunk` is
// `{order, title, content}`.

import { useEffect, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { Pager } from "@/components/admin/shared/ui-bits";

type KbSourceListItem = Schemas["KbSource"];
type KbChunkItem = Schemas["KbChunk"];

// Số đoạn/trang - phân trang BẮT BUỘC (xem `chunksQuerySchema`, server không
// nhận limit > 100): một nguồn dài có thể cắt ra hàng nghìn đoạn.
const KICH_TRANG = 20;

/**
 * I21: xem lại đoạn bot THẬT SỰ đọc ra từ một nguồn đã nạp. Không cần đẹp,
 * cần ĐÚNG - đây là cách duy nhất người vận hành (không phải lập trình viên)
 * tự phát hiện lỗi đọc file (bảng excel đọc lộn cột, PDF quét ảnh ra chữ rác)
 * mà không phải bật `AGENT_TRACE_ENABLED` rồi tự đi lục trang Trace.
 */
export function KbChunksModal({
  source,
  onClose,
}: {
  source: KbSourceListItem;
  onClose: () => void;
}) {
  const [fetched, setFetched] = useState<KbChunkItem[] | null>(null);
  const [page, setPage] = useState(0);
  const [loi, setLoi] = useState("");
  const nen = useChotNen(onClose);

  useEffect(() => {
    let huy = false;
    setFetched(null);
    setLoi("");
    unwrap(
      http.GET("/api/v1/admin/kb/sources/{source_id}/chunks", {
        params: {
          path: { source_id: source.id },
          // one extra row: its presence means there is a next page
          query: { offset: page * KICH_TRANG, limit: KICH_TRANG + 1 },
        },
      }),
    )
      .then((d) => {
        if (huy) return;
        setFetched(d);
      })
      .catch((err: unknown) => {
        if (huy) return;
        setFetched([]);
        setLoi(errorMessage(err));
      });
    return () => {
      huy = true;
    };
  }, [source.id, page]);

  const total = source.chunk_count ?? 0;
  const items = fetched?.slice(0, KICH_TRANG) ?? null;

  const hasMore = (fetched?.length ?? 0) > KICH_TRANG;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]"
      {...nen}
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl bg-surface shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="truncate font-semibold text-ink">Đoạn đã cắt - {source.name}</div>
            <div className="text-[12px] text-ink-soft">{total} đoạn</div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 cursor-pointer rounded-lg border border-line px-3 py-1 text-[13px] text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {items === null && !loi && <p className="text-[13px] text-ink-soft">Đang tải...</p>}
          {loi && <p className="text-[13px] text-red-600 dark:text-red-400">{loi}</p>}
          {items !== null && items.length === 0 && !loi && (
            <p className="py-10 text-center text-[13px] leading-relaxed text-ink-soft/60">
              Chưa có đoạn nào - nguồn có thể đang chờ xử lý, hoặc chưa cắt được đoạn nào
            </p>
          )}
          {items?.map((d) => (
            <div key={d.order} className="gc-tile space-y-1">
              {/* break-words như `noiDung`: tiêu đề là breadcrumb ghép nhiều
                  cấp ("H1 > H2 > H3") nên dài hơn ô là chuyện thường */}
              {d.title && (
                <div className="text-[12px] font-medium break-words text-brand-600 dark:text-brand-400">
                  {d.title}
                </div>
              )}
              <p className="text-[13px] leading-[1.6] break-words whitespace-pre-wrap text-ink">
                {d.content}
              </p>
            </div>
          ))}
        </div>

        {(total > KICH_TRANG || page > 0 || hasMore) && (
          <div className="flex items-center justify-end border-t border-line px-5 py-3">
            <Pager page={page} hasMore={hasMore} onPage={setPage} />
          </div>
        )}
      </div>
    </div>
  );
}
