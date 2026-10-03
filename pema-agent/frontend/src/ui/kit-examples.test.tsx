// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { KitExamples } from "./kit-examples";

afterEach(() => cleanup());

describe("KitExamples", () => {
  it("renders_every_component_family_of_the_kit", () => {
    render(<KitExamples />);

    expect(screen.getByRole("heading", { level: 1, name: "Bộ thành phần giao diện" })).toBeTruthy();
    expect(screen.getByRole("tablist", { name: "Ví dụ thẻ ngăn" })).toBeTruthy();
    expect(screen.getByLabelText(/Họ và tên/)).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Dịch vụ" })).toBeTruthy();
    expect(screen.getByText("Chưa có dữ liệu")).toBeTruthy();
  });

  it("opens_and_closes_the_example_dialog", async () => {
    render(<KitExamples />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Mở hộp thoại" }));
    expect(screen.getByRole("dialog", { name: "Hộp thoại mẫu" })).toBeTruthy();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
