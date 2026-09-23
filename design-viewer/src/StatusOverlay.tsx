import { Icon } from './Icon';
import type { FrameStatus } from './useDcFrame';

type StatusOverlayProps = { status: FrameStatus; onRetry: () => void };

export function StatusOverlay({ status, onRetry }: StatusOverlayProps) {
  if (status === 'error') {
    return (
      <div className="status status-error" role="alert">
        <Icon name="error" />
        <div>
          <strong>Trang chưa khởi động được</strong>
          <p>Runtime .dc tải React từ unpkg.com. Kiểm tra kết nối mạng hoặc lỗi trong file rồi thử lại.</p>
        </div>
        <button type="button" className="btn" onClick={onRetry}>
          Thử lại
        </button>
      </div>
    );
  }
  return (
    <div className="status" role="status">
      <span className="spinner" aria-hidden="true" />
      Đang khởi động trang…
    </div>
  );
}
