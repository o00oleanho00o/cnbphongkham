// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Card } from "./card";

afterEach(() => cleanup());

describe("Card", () => {
  it("shows_title_subtitle_and_aside_in_its_header", () => {
    render(
      <Card title="Lịch hôm nay" subtitle="24 lịch hẹn" aside={<button>Xem tất cả</button>}>
        nội dung
      </Card>,
    );

    expect(screen.getByRole("heading", { name: "Lịch hôm nay" })).toBeTruthy();
    expect(screen.getByText("24 lịch hẹn")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Xem tất cả" })).toBeTruthy();
  });

  it("has_no_header_without_title_or_aside", () => {
    const { container } = render(<Card>chỉ nội dung</Card>);

    expect(container.querySelector("header")).toBeNull();
  });

  it("drops_its_padding_when_it_wraps_a_table", () => {
    const { container } = render(<Card padded={false}>bảng</Card>);

    expect(container.firstElementChild?.className).not.toContain("p-4");
  });
});
