// ported from: web/src/shared/use-theme.ts
//
// Deviation (SSR): Next renders client components on the server first, where there is no DOM. The
// original `useState(themeHienTai)` would throw there and, on the client, disagree with the server
// HTML. The hook is now `useSyncExternalStore` over the SAME out-of-React subscriber set the original
// used: the server snapshot is "light", the client snapshot reads the class the inline script in
// `layout.tsx` already wrote on <html>, so there is still no flash and no hydration mismatch.
import { useCallback, useEffect, useSyncExternalStore } from "react";

/**
 * Chế độ sáng/tối. Lựa chọn của người dùng lưu ở `localStorage`; chưa chọn lần
 * nào thì theo cài đặt hệ điều hành (`prefers-color-scheme`).
 *
 * Class `.dark` gắn trên `<html>` (không phải `<body>`) vì `globals.css` khai
 * `@custom-variant dark (&:where(.dark, .dark *))` - phải là tổ tiên của MỌI
 * phần tử, kể cả thứ render qua portal ra ngoài body.
 *
 * Class được ghi ngay trong `layout.tsx` trước khi React chạy - hook này chỉ
 * đọc lại trạng thái đã có (tránh một khung sáng rồi mới tối lại).
 *
 * MỌI nơi gọi hook phải thấy CÙNG một giá trị: `SidebarNav` chứa nút bấm, còn
 * trang đăng nhập cần `theme` để chọn ảnh nền. Trạng thái để ở NGOÀI React và
 * các hook đăng ký nhận thông báo chung.
 */

export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "pema-agent-theme";
const KEY = THEME_STORAGE_KEY;

/** Đọc trạng thái ĐANG hiệu lực từ chính DOM, không đoán lại từ localStorage */
function themeHienTai(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

/** Mọi hook đang mounted - gọi hết khi theme đổi để chúng cùng re-render */
const nguoiTheoDoi = new Set<() => void>();

function phatTin(): void {
  for (const bao of nguoiTheoDoi) bao();
}

function dangKy(bao: () => void): () => void {
  nguoiTheoDoi.add(bao);
  return () => {
    nguoiTheoDoi.delete(bao);
  };
}

/** Đổi theme: ghi DOM + localStorage rồi báo cho MỌI hook đang dùng */
function datTheme(moi: Theme): void {
  document.documentElement.classList.toggle("dark", moi === "dark");
  try {
    localStorage.setItem(KEY, moi);
  } catch {
    /* localStorage bị chặn (chế độ riêng tư): vẫn đổi được trong phiên này */
  }
  phatTin();
}

function themeMayChu(): Theme {
  return "light";
}

export function useTheme(): { theme: Theme; toggle: () => void } {
  const theme = useSyncExternalStore(dangKy, themeHienTai, themeMayChu);

  const toggle = useCallback(() => {
    datTheme(themeHienTai() === "dark" ? "light" : "dark");
  }, []);

  /**
   * Người dùng đổi chế độ ở HỆ ĐIỀU HÀNH trong lúc đang mở tab: đổi theo, NHƯNG
   * chỉ khi họ chưa từng tự chọn trên dashboard - đã chọn tay rồi mà bị hệ điều
   * hành ghi đè thì cái nút kia thành vô nghĩa.
   */
  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => {
      let daChon: string | null = null;
      try {
        daChon = localStorage.getItem(KEY);
      } catch {
        /* không đọc được thì coi như chưa chọn */
      }
      if (daChon) return;
      document.documentElement.classList.toggle("dark", e.matches);
      phatTin();
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return { theme, toggle };
}
