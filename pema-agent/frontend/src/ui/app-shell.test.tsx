// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { AppShell } from "./app-shell";

afterEach(() => cleanup());

describe("AppShell", () => {
  it("places_sidebar_top_bar_content_and_tab_bar_and_offers_a_skip_link", () => {
    render(
      <AppShell
        sidebar={<aside>thanh bên</aside>}
        topBar={<header>đầu trang</header>}
        tabBar={<nav>tab</nav>}
      >
        <p>nội dung</p>
      </AppShell>,
    );

    expect(screen.getByText("thanh bên")).toBeTruthy();
    expect(screen.getByText("đầu trang")).toBeTruthy();
    expect(screen.getByText("tab")).toBeTruthy();
    expect(screen.getByRole("main").textContent).toBe("nội dung");
    expect(screen.getByRole("link", { name: "Đến nội dung chính" }).getAttribute("href")).toBe(
      "#main",
    );
  });

  it("makes_the_main_area_the_scroll_container_from_lg", () => {
    render(
      <AppShell sidebar={null} topBar={null}>
        x
      </AppShell>,
    );

    expect(screen.getByRole("main").className).toContain("lg:overflow-y-auto");
  });
});
