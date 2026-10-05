// ported from: web/src/pages/session-trace-view.tsx
"use client";

// Deviations: typed client (`GET /admin/traces/{account_id}/{thread_id}` then `GET /admin/traces/turn/{id}`);
// `TraceTurnRow` has `steps` and `total_tokens` (no separate `stepCount`); step rows are adapted to the
// original `TraceStep` by `traceStepTuApi`. Traces may contain message text: staff-only (`admin.usage`).

import { useEffect, useState, useRef } from "react";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { traceStepTuApi, type TraceStep } from "@/lib/admin/traces/trace-types";

type TraceTurn = Schemas["TraceTurnRow"];
import { formatTime } from "@/components/admin/shared/ui-bits";
import { TraceRong, TraceStepCard } from "@/components/admin/traces/trace-step-card";

/**
 * Tab Trace trong drawer Sessions: các lượt agent của MỘT hội thoại.
 * Trang /trace ở sidebar là bản gộp mọi hội thoại, dùng chung card step.
 */
export function SessionTraceView({ accountId, threadId }: { accountId: string; threadId: string }) {
  const [turns, setTurns] = useState<TraceTurn[]>([]);
  const [dangMo, setDangMo] = useState<number | null>(null);
  const [steps, setSteps] = useState<TraceStep[]>([]);
  const [dangTai, setDangTai] = useState(false);

  useEffect(() => {
    unwrap(
      http.GET("/api/v1/admin/traces/{account_id}/{thread_id}", {
        params: { path: { account_id: accountId, thread_id: threadId } },
      }),
    )
      .then((r) => setTurns(r.turns))
      .catch(() => setTurns([]));
  }, [accountId, threadId]);

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
    const rows = await unwrap(
      http.GET("/api/v1/admin/traces/turn/{turn_id}", { params: { path: { turn_id: turnId } } }),
    ).catch(() => []);
    // Bấm lượt A rồi lượt B khi A chưa về: response A về SAU sẽ ghi đè và UI
    // hiện step của A dưới tiêu đề của B. Trên trang chẩn đoán thì nhầm lẫn đó
    // đắt - người đọc kết luận sai về đúng cái lượt họ đang truy.
    if (luotDangMo.current !== turnId) return;
    setSteps(rows.map(traceStepTuApi));
    setDangTai(false);
  }

  if (turns.length === 0) return <TraceRong />;

  return (
    <div className="space-y-2">
      {turns.map((t) => (
        <div key={t.id}>
          <button
            type="button"
            onClick={() => moLuot(t.id)}
            className="flex w-full items-center justify-between rounded-xl border border-line bg-surface px-4 py-2.5 text-left hover:bg-tile"
          >
            <div>
              <div className="text-[13px] font-medium text-ink">
                {t.steps} step - {t.total_tokens.toLocaleString("vi-VN")} token
              </div>
              <div className="text-[11px] text-ink-soft/60">{formatTime(t.created_at)}</div>
            </div>
            <span className="text-[12px] text-ink-soft">{dangMo === t.id ? "Thu gọn" : "Xem"}</span>
          </button>

          {dangMo === t.id && (
            <div className="mt-2 space-y-2 pl-2">
              {dangTai && <p className="text-[12px] text-ink-soft">Đang tải...</p>}
              {!dangTai && steps.map((s, i) => <TraceStepCard key={i} step={s} />)}
              {!dangTai && steps.length === 0 && (
                <p className="text-[12px] text-ink-soft">Lượt này không có step nào được ghi.</p>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
