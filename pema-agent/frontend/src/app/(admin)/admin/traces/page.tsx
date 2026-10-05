// ported from: web/src/pages/trace-page.tsx
"use client";

// Deviations: `useSearchParams` of next (the page needs a Suspense boundary, added in the default export);
// typed client: `GET /admin/traces` (cursor `before`, `next_cursor`) and `GET /admin/traces/turn/{id}` whose
// rows are adapted to the original `TraceStep`; turn rows carry `thread_name`, `steps`, `total_tokens`.
// The link from the schedule history is `/admin/traces?turnId=`. Traces may contain message text.

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, useRef } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { traceStepTuApi, type TraceStep } from "@/lib/admin/traces/trace-types";

type TraceTurnAcrossThreads = Schemas["TraceTurnRow"];

const loadSteps = (turnId: number) =>
  unwrap(
    http.GET("/api/v1/admin/traces/turn/{turn_id}", { params: { path: { turn_id: turnId } } }),
  ).then((rows) => rows.map(traceStepTuApi));
import { PageHeader } from "@/components/admin/layout/page-header";
import { formatTime } from "@/components/admin/shared/ui-bits";
import { TraceRong, TraceStepCard } from "@/components/admin/traces/trace-step-card";

/**
 * Trang Trace: các lượt agent gần đây của MỌI hội thoại.
 *
 * Vì sao có trang riêng dù đã có tab trong drawer Sessions: bản đầu chỉ đặt
 * trong drawer, user đi tìm và không thấy - tính năng chẩn đoán mà chôn sâu ba
 * lớp thì coi như không có. Ở đây bấm một cái là thấy hết, không phải nhớ lỗi
 * xảy ra ở hội thoại nào.
 *
 * Hỗ trợ mở thẳng 1 lượt qua `?turnId=` (drawer lịch sử chạy của trang Lịch
 * hẹn dùng link này để nhảy tới đúng lượt agent của 1 lần job chạy) - tách
 * hẳn khỏi state của danh sách `turns` vì lượt đó có thể đã rơi khỏi 50 lượt
 * gần nhất, không tìm cách "highlight trong list" mà tự fetch riêng.
 */
function TracePage() {
  const searchParams = useSearchParams();
  const openTurnId = Number(searchParams.get("turnId"));

  const [turns, setTurns] = useState<TraceTurnAcrossThreads[]>([]);
  const [dangMo, setDangMo] = useState<number | null>(null);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [dangTai, setDangTai] = useState(false);
  const [loi, setLoi] = useState("");

  const [openSteps, setOpenSteps] = useState<TraceStep[]>([]);
  const [openLoading, setOpenLoading] = useState(false);

  /** Con trỏ trang sau; `null` = đã hết lượt, ẩn nút "Xem thêm" */
  const [conTro, setConTro] = useState<number | null>(null);
  const [dangTaiThem, setDangTaiThem] = useState(false);

  useEffect(() => {
    unwrap(http.GET("/api/v1/admin/traces", { params: { query: { limit: 50 } } }))
      .then((r) => {
        setTurns(r.turns);
        setConTro(r.next_cursor ?? null);
      })
      .catch((e: unknown) => setLoi(errorMessage(e)));
  }, []);

  /** Nối thêm trang lượt CŨ HƠN. Không đụng lượt đang mở ở trên. */
  async function xemThem() {
    if (conTro === null) return;
    setDangTaiThem(true);
    try {
      const r = await unwrap(
        http.GET("/api/v1/admin/traces", { params: { query: { before: conTro, limit: 50 } } }),
      );
      setTurns((cu) => [...cu, ...r.turns]);
      setConTro(r.next_cursor ?? null);
    } catch (e) {
      setLoi(errorMessage(e));
    } finally {
      setDangTaiThem(false);
    }
  }

  useEffect(() => {
    if (!Number.isInteger(openTurnId) || openTurnId <= 0) return;
    setOpenLoading(true);
    loadSteps(openTurnId)
      .then(setOpenSteps)
      .catch(() => setOpenSteps([]))
      .finally(() => setOpenLoading(false));
  }, [openTurnId]);

  // Lượt ĐANG mở, đọc được ngay lúc response về. Không dùng state `dangMo` cho
  // việc này: closure của hàm bất đồng bộ giữ giá trị của lần render lúc bấm.
  const luotDangMo = useRef<number | null>(null);

  async function moLuot(turnId: number) {
    if (dangMo === turnId) {
      luotDangMo.current = null;
      setDangMo(null);
      return;
    }
    luotDangMo.current = turnId;
    setDangMo(turnId);
    setDangTai(true);
    const found = await loadSteps(turnId).catch((): TraceStep[] => []);
    // Bấm lượt A rồi lượt B khi A chưa về: response A về SAU sẽ ghi đè và UI
    // hiện step của A dưới tiêu đề của B. Trên trang chẩn đoán thì nhầm lẫn đó
    // đắt - người đọc kết luận sai về đúng cái lượt họ đang truy.
    if (luotDangMo.current !== turnId) return;
    setSteps(found);
    setDangTai(false);
  }

  return (
    <>
      <PageHeader
        title="Trace agent"
        subtitle="Mỗi lượt bot trả lời đã chạy qua những step nào: model nói gì, gọi tool nào với tham số gì"
      />

      {loi && (
        <div className="mb-4 rounded-tile border border-danger-line bg-danger-soft px-4 py-2.5 text-small text-danger">
          {loi}
        </div>
      )}

      {Number.isInteger(openTurnId) && openTurnId > 0 && (
        <div className="mb-5 rounded-tile border border-brand-100 bg-brand-50/40 p-4">
          <div className="mb-2 text-small font-semibold text-brand-700">
            Lượt #{openTurnId} (mở từ Lịch hẹn)
          </div>
          {openLoading && <p className="text-label text-ink-soft">Đang tải...</p>}
          {!openLoading && openSteps.map((s, i) => <TraceStepCard key={i} step={s} />)}
          {!openLoading && openSteps.length === 0 && (
            <p className="text-label text-ink-soft">Lượt này không có step nào được ghi.</p>
          )}
        </div>
      )}

      {turns.length === 0 && !loi && <TraceRong />}

      <div className="space-y-2">
        {turns.map((t) => (
          <div key={t.id}>
            <button
              type="button"
              onClick={() => moLuot(t.id)}
              className="flex w-full items-center justify-between rounded-tile border border-line bg-surface px-5 py-3 text-left hover:bg-tile"
            >
              <div className="min-w-0">
                <div className="truncate text-body font-medium text-ink">
                  {t.thread_name || t.thread_id}
                </div>
                <div className="text-micro text-ink-soft/60">
                  {formatTime(t.created_at)} - {t.steps} step -{" "}
                  {t.total_tokens.toLocaleString("vi-VN")} token
                </div>
              </div>
              <span className="shrink-0 text-label text-ink-soft">
                {dangMo === t.id ? "Thu gọn" : "Xem"}
              </span>
            </button>

            {dangMo === t.id && (
              <div className="mt-2 space-y-2 pl-3">
                {dangTai && <p className="text-label text-ink-soft">Đang tải...</p>}
                {!dangTai && steps.map((s, i) => <TraceStepCard key={i} step={s} />)}
                {!dangTai && steps.length === 0 && (
                  <p className="text-label text-ink-soft">Lượt này không có step nào được ghi.</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Chỉ hiện khi server nói còn lượt phía sau. Bấm là NỐI THÊM, lượt đang
          mở ở trên không bị đóng lại. */}
      {conTro !== null && (
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            onClick={() => void xemThem()}
            disabled={dangTaiThem}
            className="rounded-control border border-line bg-surface px-4 py-2 text-small font-medium text-ink hover:bg-tile disabled:opacity-50"
          >
            {dangTaiThem ? "Đang tải..." : "Xem thêm lượt cũ hơn"}
          </button>
        </div>
      )}

      {conTro === null && turns.length > 0 && (
        <p className="mt-4 text-center text-label text-ink-soft/60">
          Đã hết lượt có trace. Trace cũ hơn bị dọn theo "Giữ trace" ở trang Cấu hình.
        </p>
      )}
    </>
  );
}

export default function TraceRoute() {
  return (
    <Suspense fallback={null}>
      <TracePage />
    </Suspense>
  );
}
