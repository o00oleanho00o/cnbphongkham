// ported from: web/src/shared/backdrop-close-guard.ts

import { useRef, type MouseEvent, type PointerEvent } from "react";

/**
 * Chốt đóng modal/drawer khi bấm ra nền.
 *
 * Vì sao không đơn giản là `onClick={onClose}` trên div nền: trình duyệt bắn
 * `click` lên TỔ TIÊN CHUNG gần nhất của điểm bấm xuống và điểm thả. Bôi đen
 * chữ trong ô nhập rồi lỡ tay kéo quá mép modal thì mousedown ở trong panel,
 * mouseup ở ngoài nền, tổ tiên chung chính là div nền - `onClick` của nền chạy
 * và modal đóng, mất sạch nội dung đang gõ. Cái `onClick={e =>
 * e.stopPropagation()}` hay gắn trên panel KHÔNG cứu được: sự kiện click đó
 * không hề đi qua panel.
 *
 * Cách chắc chắn: chỉ đóng khi CẢ điểm bấm xuống LẪN điểm thả đều rơi đúng vào
 * div nền. Hệ quả: bấm ngoài rồi thả vào trong panel cũng không đóng - đúng ý
 * "chỉ nhấp hẳn bên ngoài mới tắt", và an toàn hơn cho ô persona 8.000 ký tự.
 */

/** Rải thẳng vào div nền: `<div className="fixed inset-0 ..." {...nen}>` */
export function useChotNen(onClose: () => void) {
  const batDauONen = useRef(false);
  return {
    onPointerDown: (e: PointerEvent) => {
      batDauONen.current = e.target === e.currentTarget;
    },
    onClick: (e: MouseEvent) => {
      const dong = batDauONen.current && e.target === e.currentTarget;
      batDauONen.current = false;
      if (dong) onClose();
    },
  };
}
