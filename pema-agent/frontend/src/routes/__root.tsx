// ported from: web/index.html, web/src/main.tsx (root document, font, theme bootstrap)
import { createRootRoute, HeadContent, Outlet, Scripts } from "@tanstack/react-router";
import type { ReactNode } from "react";

import appCss from "@/globals.css?url";

/**
 * Gắn class .dark TRƯỚC khi React render (bản gốc: script inline trong index.html). Để việc này cho
 * useEffect thì trang vẽ xong một khung sáng rồi mới tối lại. Chạy đồng bộ, trong <head>, trước bundle.
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

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Pema CSKH" },
      {
        name: "description",
        content: "Chăm sóc khách hàng và quản trị trợ lý AI của Pema Digital Clinic",
      },
      { name: "theme-color", content: "#0b4f94" },
    ],
    links: [
      { rel: "stylesheet", href: appCss },
      { rel: "icon", href: "/pema-logo.png" },
      { rel: "apple-touch-icon", href: "/pema-logo.png" },
    ],
    scripts: [{ children: THEME_BOOTSTRAP }],
  }),
  component: RootDocument,
});

function RootDocument(): ReactNode {
  return (
    <html lang="vi" suppressHydrationWarning>
      <head>
        <HeadContent />
      </head>
      <body>
        <Outlet />
        <Scripts />
      </body>
    </html>
  );
}
