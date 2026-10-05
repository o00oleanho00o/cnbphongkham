"use client";

import type { LiveMode } from "@/lib/live/live-connection";

/** Shown only when the live stream has been down for over 10 seconds and the screen refreshes on a timer. */
export function LiveStatus({ mode }: { mode: LiveMode }) {
  if (mode !== "polling") return null;
  return (
    <p
      role="status"
      className="mb-3 rounded-control border border-warning-line bg-warning-soft px-3 py-2 text-label text-ink"
    >
      Mất kết nối cập nhật trực tiếp. Danh sách tự làm mới mỗi 30 giây, hệ thống sẽ nối lại khi có
      thể.
    </p>
  );
}
