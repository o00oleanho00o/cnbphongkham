// ported from: web/src/pages/trace-step-card.tsx
"use client";

import { useState } from "react";
import type { TraceStep } from "@/lib/admin/traces/trace-types";

/**
 * Hiển thị một step agent. Tách file riêng vì dùng ở hai chỗ: trang Trace
 * (gộp mọi hội thoại) và tab Trace trong drawer Sessions (theo một hội thoại).
 *
 * Thứ tự trình bày có chủ đích: CẢNH BÁO lên trước cùng, vì đó là chỗ nhà cung
 * cấp báo tham số bị âm thầm bỏ qua - loại lỗi tốn nhiều thời gian nhất để tìm.
 */

/**
 * Khối chữ dài: cắt bớt chiều cao, bấm để bung hết.
 *
 * KHÔNG dùng khung cuộn riêng (`overflow-auto`): một step có cả chục khối như
 * này, mỗi khối một thanh cuộn thì con lăn chuột bị khối bên dưới con trỏ bắt
 * mất, phải rê ra tận lề mới cuộn được trang. Cắt + bung là thao tác rõ ràng hơn.
 */
function KhoiChu({ nhan, noiDung, mau }: { nhan: string; noiDung: string; mau?: string }) {
  const [bung, setBung] = useState(false);
  if (!noiDung) return null;

  // Ước lượng theo số dòng: dài hơn chừng này mới cần nút bung
  const daiQua = noiDung.length > 260 || noiDung.split("\n").length > 5;

  return (
    <div className="mt-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-eyebrow font-semibold tracking-[0.1em] text-ink-soft/60 uppercase">
          {nhan}
        </span>
        {daiQua && (
          <button
            type="button"
            onClick={() => setBung((v) => !v)}
            className="shrink-0 text-micro text-ink-soft hover:text-ink"
          >
            {bung ? "Thu gọn" : "Xem đầy đủ"}
          </button>
        )}
      </div>
      <pre
        className={`overflow-hidden rounded-control px-3 py-2 text-label leading-relaxed break-words whitespace-pre-wrap ${
          daiQua && !bung ? "max-h-32" : ""
        } ${mau ?? "bg-tile text-ink-soft"}`}
      >
        {noiDung}
      </pre>
    </div>
  );
}

export function TraceStepCard({ step }: { step: TraceStep }) {
  return (
    <div className="rounded-tile border border-line bg-surface p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-brand-50 px-1.5 py-0.5 text-micro font-medium text-brand-700">
          Step {step.stepNumber}
        </span>
        {/* Chỉ hiện khi CÓ chạy lại: lượt bình thường mà dán "lần 1" lên mọi
            step chỉ làm nhiễu. Thấy nhãn này tức là step đánh số lại từ đầu,
            không phải model đang lặp. */}
        {step.attempt > 1 && (
          <span className="rounded bg-warning-soft px-1.5 py-0.5 text-micro font-medium text-warning">
            chạy lại lần {step.attempt}
          </span>
        )}
        {step.finishReason && (
          <span className="rounded bg-tile px-1.5 py-0.5 text-micro text-ink-soft">
            {step.finishReason}
          </span>
        )}
        <span className="text-micro text-ink-soft/60">
          {step.inputTokens.toLocaleString("vi-VN")} vào /{" "}
          {step.outputTokens.toLocaleString("vi-VN")} ra
        </span>
      </div>

      {step.warnings.length > 0 && (
        <div className="mt-2 rounded-control border border-warning-line bg-warning-soft px-3 py-2">
          <div className="mb-1 text-eyebrow font-semibold tracking-[0.1em] text-warning uppercase">
            Cảnh báo từ nhà cung cấp
          </div>
          {step.warnings.map((w, i) => (
            <div key={i} className="text-label text-warning">
              {w}
            </div>
          ))}
        </div>
      )}

      {/* Đặt TRƯỚC mọi khối khác: tool hỏng là kết cục của step, đọc nó trước
          rồi mới xuống chi tiết. Trước khi có khối này, step tool lỗi hiện
          "Gọi tool" rồi cụt - nhìn y hệt lượt đang chạy dở. */}
      {step.toolErrors.length > 0 && (
        <div className="mt-2 rounded-control border border-danger-line bg-danger-soft px-3 py-2">
          <div className="mb-1 text-eyebrow font-semibold tracking-[0.1em] text-danger uppercase">
            Tool chạy lỗi
          </div>
          {step.toolErrors.map((e, i) => (
            <div key={i} className="text-label leading-[1.6] text-danger">
              <span className="font-medium">{e.name}</span>: {e.error}
            </div>
          ))}
        </div>
      )}

      <KhoiChu nhan="Model suy nghĩ" noiDung={step.reasoning} mau="bg-brand-50 text-brand-700" />
      <KhoiChu nhan="Model nói" noiDung={step.text} />

      {step.toolCalls.map((c, i) => (
        <KhoiChu
          key={`c${i}`}
          nhan={`Gọi tool: ${c.name}`}
          noiDung={c.input}
          mau="bg-info-soft text-info"
        />
      ))}
      {/* Nhánh HỎNG tô đỏ như khối "Tool chạy lỗi" ở trên. Dùng cờ `hong` do
          `summarizeStep` gắn, KHÔNG dò chữ trong `output` - nội dung web của
          người lạ đi thẳng vào đó nên luật dựa trên chữ có thể bị soạn cho
          trùng. Bản ghi cũ không có cờ thì hiện như cũ. */}
      {step.toolResults.map((r, i) => (
        <KhoiChu
          key={`r${i}`}
          nhan={`Tool trả về: ${r.name}${r.hong ? " (hỏng)" : ""}`}
          noiDung={r.output}
          mau={r.hong ? "bg-danger-soft text-danger" : undefined}
        />
      ))}
    </div>
  );
}

/** Câu giải thích khi chưa có trace nào - dùng chung cho cả hai chỗ */
export function TraceRong() {
  return (
    <p className="py-10 text-center text-small leading-relaxed text-ink-soft/60">
      Chưa có trace nào.
      <br />
      Trace chỉ ghi từ lúc bật AGENT_TRACE_ENABLED, và tự dọn sau AGENT_TRACE_RETENTION_DAYS ngày.
    </p>
  );
}
