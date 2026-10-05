// ported from: web/index.html, web/src/main.tsx (root document, font, theme bootstrap)
import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import Script from "next/script";
import type { ReactNode } from "react";

import "./globals.css";

/** Local Be Vietnam Pro (OFL, see fonts/be-vietnam-pro-OFL.txt): full Vietnamese diacritics, no CDN. */
const beVietnamPro = localFont({
  src: [
    { path: "./fonts/be-vietnam-pro-regular.ttf", weight: "400", style: "normal" },
    { path: "./fonts/be-vietnam-pro-medium.ttf", weight: "500", style: "normal" },
    { path: "./fonts/be-vietnam-pro-semibold.ttf", weight: "600", style: "normal" },
    { path: "./fonts/be-vietnam-pro-bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-be-vietnam-pro",
  display: "swap",
});

export const metadata: Metadata = {
  title: { default: "Pema CSKH", template: "%s · Pema CSKH" },
  description: "Chăm sóc khách hàng và quản trị trợ lý AI của Pema Digital Clinic",
  icons: { icon: "/pema-logo.png", apple: "/pema-logo.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b4f94",
};

/**
 * Gắn class .dark TRƯỚC khi React render (bản gốc: script inline trong index.html). Để việc này cho
 * useEffect thì trang vẽ xong một khung sáng rồi mới tối lại. Chạy đồng bộ, trước bundle.
 */
const THEME_BOOTSTRAP = `(function () {
  try {
    var luu = localStorage.getItem("pema-agent-theme");
    var toi = luu ? luu === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (toi) document.documentElement.classList.add("dark");
  } catch (e) {
    /* localStorage bị chặn (chế độ riêng tư): cứ để giao diện sáng */
  }
})();`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className={beVietnamPro.variable} suppressHydrationWarning>
      <body>
        <Script id="theme-bootstrap" strategy="beforeInteractive">
          {THEME_BOOTSTRAP}
        </Script>
        {children}
      </body>
    </html>
  );
}
