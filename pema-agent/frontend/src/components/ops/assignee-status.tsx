"use client";

// One line under a "Phụ trách" box saying what is going on with the list of colleagues: still loading, or it could
// not be read (with "Thử lại"). The box itself keeps working in both cases ("Tôi" and "Giữ nguyên" are always
// there), so this is a hint and not an error screen. Nothing is rendered once the list is there.
export function AssigneeStatus({
  loading,
  error,
  onRetry,
}: {
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  if (error) {
    return (
      <p role="status" className="mt-1 text-label text-ink-soft">
        Chưa tải được danh sách nhân viên, tạm thời chỉ chọn &quot;Tôi&quot; hoặc giữ nguyên.{" "}
        <button type="button" onClick={onRetry} className="font-medium text-brand-500 underline">
          Thử lại
        </button>
      </p>
    );
  }
  if (loading) {
    return (
      <p role="status" className="mt-1 text-label text-ink-soft">
        Đang tải danh sách nhân viên...
      </p>
    );
  }
  return null;
}
