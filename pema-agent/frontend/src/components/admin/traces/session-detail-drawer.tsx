// ported from: web/src/pages/session-detail-drawer.tsx
"use client";

// Deviations (contract `ThreadRow` / `StoredMessage`): the thread row carries no `summary` nor token
// `usage`, so the summary block and the token total are gone and "Xóa bản tóm tắt" is a plain action;
// `DELETE .../history` has no "also delete memory" flag, so that tick box is gone (memory facts are deleted
// one by one on the memory page); attached images are never loaded here, only counted (patient photos are
// not shown or analysed by this screen). Messages page by `before_id`.

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type ThreadItem = Schemas["ThreadRow"];
type MessageItem = Schemas["StoredMessage"];
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { formatTime } from "@/components/admin/shared/ui-bits";
import { SessionTraceView } from "@/components/admin/traces/session-trace-view";

/**
 * Drawer trượt từ phải: xem hội thoại của 1 thread, nút tải thêm tin cũ hơn.
 * Tab "Trace" xem lại từng step agent đã chạy - dùng khi bot trả lời sai và cần
 * biết nó đã gọi tool nào với tham số gì.
 */
export function SessionDetailDrawer({
  thread,
  onClose,
  onDoiDuLieu,
}: {
  thread: ThreadItem;
  onClose: () => void;
  /** Gọi khi dữ liệu thread đổi (xóa ngữ cảnh) để danh sách ngoài tải lại */
  onDoiDuLieu?: () => void;
}) {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [hasOlder, setHasOlder] = useState(false);
  const [tab, setTab] = useState<"chat" | "trace">("chat");
  const [dangXoa, setDangXoa] = useState(false);
  const [dangXoaNguCanh, setDangXoaNguCanh] = useState(false);
  const [loi, setLoi] = useState("");
  const { confirm, confirmDialog } = useConfirmDialog();

  useEffect(() => {
    unwrap(
      http.GET("/api/v1/admin/threads/{account_id}/{thread_id}/messages", {
        params: {
          path: { account_id: thread.account_id, thread_id: thread.thread_id },
          query: { limit: 50 },
        },
      }),
    )
      .then((items) => {
        setMessages(items);
        setHasOlder(items.length >= 50);
      })
      .catch((e: unknown) => setLoi(errorMessage(e)));
  }, [thread.account_id, thread.thread_id]);

  const nen = useChotNen(onClose);

  const khungCuon = useRef<HTMLDivElement>(null);
  const daCuonLanDau = useRef(false);
  /** Khoảng cách từ đáy TRƯỚC khi chèn tin cũ - dùng để trả về đúng chỗ đang đọc */
  const giuKhoangDay = useRef<number | null>(null);

  /**
   * Cuộn như một khung chat thật: mở ra là ở TIN MỚI NHẤT, lướt lên mới thấy
   * tin cũ.
   *
   * Bản đầu không cuộn gì cả nên khung đứng ở `scrollTop = 0`, tức tin CŨ NHẤT
   * trong 50 tin vừa nạp - mở hội thoại ra thấy chuyện của mấy hôm trước.
   *
   * `useLayoutEffect` chứ không phải `useEffect`: chạy trước lượt vẽ nên không
   * thấy khung nháy ở đầu danh sách rồi mới nhảy xuống.
   */
  useLayoutEffect(() => {
    const el = khungCuon.current;
    if (!el || messages.length === 0) return;

    // Vừa chèn tin cũ lên đầu: giữ nguyên chỗ đang đọc. Không giữ thì màn hình
    // nhảy vọt đúng lúc người ta đang đọc dở.
    if (giuKhoangDay.current !== null) {
      el.scrollTop = el.scrollHeight - giuKhoangDay.current;
      giuKhoangDay.current = null;
      return;
    }

    if (!daCuonLanDau.current) {
      daCuonLanDau.current = true;
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  async function xoaTomTat() {
    const ok = await confirm({
      title: "Xóa bản tóm tắt này?",
      message:
        "Tin nhắn KHÔNG bị xóa. Bot sẽ tự viết lại bản tóm tắt từ đầu ở lần gộp tiếp theo, nên nó tốn thêm một lượt gọi model.",
    });
    if (!ok) return;
    setDangXoa(true);
    setLoi("");
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/threads/{account_id}/{thread_id}/summary", {
          params: { path: { account_id: thread.account_id, thread_id: thread.thread_id } },
        }),
      );
    } catch (e) {
      setLoi(errorMessage(e));
    } finally {
      setDangXoa(false);
    }
  }

  async function xoaNguCanh() {
    const ok = await confirm({
      title: "Xóa sạch ngữ cảnh cuộc trò chuyện này?",
      message:
        "Toàn bộ tin nhắn, bản tóm tắt, trace từng bước và ảnh đã tải của cuộc trò chuyện này sẽ bị xóa. " +
        "Bot vẫn giữ những điều đã ghi nhớ về người này (xóa riêng ở trang Trí nhớ). " +
        "Lịch hẹn đang chờ vẫn giữ nguyên. Không hoàn tác được.",
    });
    if (!ok) return;
    setDangXoaNguCanh(true);
    setLoi("");
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/threads/{account_id}/{thread_id}/history", {
          params: { path: { account_id: thread.account_id, thread_id: thread.thread_id } },
        }),
      );
      setMessages([]);
      setHasOlder(false);
      onDoiDuLieu?.();
    } catch (e) {
      setLoi(errorMessage(e));
    } finally {
      setDangXoaNguCanh(false);
    }
  }

  async function loadOlder() {
    const oldestId = messages[0]?.id;
    if (!oldestId) return;
    // Đo TRƯỚC khi chèn: khoảng cách tới đáy là thứ duy nhất không đổi khi
    // chiều cao danh sách tăng lên.
    const el = khungCuon.current;
    giuKhoangDay.current = el ? el.scrollHeight - el.scrollTop : null;
    const items = await unwrap(
      http.GET("/api/v1/admin/threads/{account_id}/{thread_id}/messages", {
        params: {
          path: { account_id: thread.account_id, thread_id: thread.thread_id },
          query: { before_id: oldestId, limit: 50 },
        },
      }),
    );
    setMessages((prev) => [...items, ...prev]);
    setHasOlder(items.length >= 50);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-ink/25 backdrop-blur-[2px]" {...nen}>
      <div className="flex h-full w-full max-w-lg flex-col border-l border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <div>
            <div className="font-semibold text-ink">{thread.display_name || thread.thread_id}</div>
            <div className="text-[12px] text-ink-soft">{thread.message_count} tin</div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-line px-3 py-1 text-[13px] text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <div className="flex gap-1 border-b border-line px-5 pt-2">
          {(
            [
              ["chat", "Hội thoại"],
              ["trace", "Trace agent"],
            ] as const
          ).map(([key, nhan]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded-t-lg px-3 py-2 text-[13px] font-medium transition-colors ${
                tab === key
                  ? "border-b-2 border-brand-500 text-brand-700"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              {nhan}
            </button>
          ))}
        </div>

        {tab === "trace" && (
          <div className="flex-1 overflow-y-auto bg-canvas px-5 py-4">
            <SessionTraceView accountId={thread.account_id} threadId={thread.thread_id} />
          </div>
        )}

        <div
          ref={khungCuon}
          className={`flex-1 space-y-3 overflow-y-auto bg-canvas px-5 py-4 ${tab === "chat" ? "" : "hidden"}`}
        >
          {hasOlder && (
            <button
              onClick={loadOlder}
              className="mx-auto block rounded-full border border-line bg-surface px-4 py-1 text-[12px] text-ink-soft hover:bg-tile"
            >
              Tải tin cũ hơn
            </button>
          )}
          {messages.map((m, index) => (
            <div
              key={m.id ?? `${m.created_at}-${index}`}
              className={m.role === "assistant" ? "flex justify-end" : "flex"}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2 text-[14px] ${
                  m.role === "assistant"
                    ? "rounded-br-md bg-brand-500 text-white"
                    : "rounded-bl-md border border-line bg-surface text-ink"
                }`}
              >
                {m.role === "user" && m.sender_name && (
                  <div className="mb-0.5 text-[12px] font-medium text-brand-600">
                    {m.sender_name}
                  </div>
                )}
                <div className="break-words whitespace-pre-wrap">{m.content}</div>
                {(m.images?.length ?? 0) > 0 && (
                  <div className="mt-1 text-[12px] italic opacity-80">
                    [{m.images?.length} ảnh đính kèm - không hiển thị ở màn này]
                  </div>
                )}
                <div
                  className={`mt-1 text-right text-[10px] ${
                    m.role === "assistant" ? "text-white/70" : "text-ink-soft/60"
                  }`}
                >
                  {formatTime(m.created_at)}
                </div>
              </div>
            </div>
          ))}
          {messages.length === 0 && (
            <p className="py-10 text-center text-[14px] text-ink-soft/60">Chưa có tin nhắn</p>
          )}
        </div>

        {/* Chân drawer - chỉ ở tab Chat, vì đây là thao tác lên chính hội thoại.
            Ô tick đứng TRƯỚC nút: người dùng phải thấy lựa chọn trí nhớ trước
            khi bấm, chứ không phải đọc nó trong hộp xác nhận rồi mới quay ra. */}
        {tab === "chat" && (
          <div className="border-t border-line bg-surface px-5 py-3">
            {loi && (
              <p role="alert" className="mb-2 text-[12px] text-red-600 dark:text-red-400">
                {loi}
              </p>
            )}
            <button
              type="button"
              onClick={xoaTomTat}
              disabled={dangXoa}
              className="mr-2 rounded-lg border border-line px-3 py-1.5 text-[13px] font-medium text-ink-soft hover:bg-tile disabled:opacity-50"
            >
              {dangXoa ? "Đang xóa..." : "Xóa bản tóm tắt"}
            </button>
            <button
              type="button"
              onClick={xoaNguCanh}
              disabled={dangXoaNguCanh}
              className="rounded-lg border border-rose-200 px-3 py-1.5 text-[13px] font-medium text-rose-600 hover:bg-rose-50 disabled:opacity-50 dark:border-rose-900 dark:text-rose-400 dark:hover:bg-rose-950/40"
            >
              {dangXoaNguCanh ? "Đang xóa..." : "Xóa sạch ngữ cảnh"}
            </button>
            <p className="mt-1.5 text-[11px] leading-relaxed text-ink-soft/70">
              Bot quên hẳn cuộc trò chuyện này và bắt đầu lại từ đầu. Lịch hẹn đang chờ vẫn giữ.
            </p>
          </div>
        )}
      </div>
      {confirmDialog}
    </div>
  );
}
