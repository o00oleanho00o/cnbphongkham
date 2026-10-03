// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EmptyState } from "./empty-state";

afterEach(() => cleanup());

describe("EmptyState", () => {
  it("says_what_is_missing_and_offers_the_action", () => {
    render(
      <EmptyState
        title="Chưa có lịch hẹn"
        hint="Tạo lịch đầu tiên"
        action={<button>Tạo lịch</button>}
      />,
    );

    expect(screen.getByText("Chưa có lịch hẹn")).toBeTruthy();
    expect(screen.getByText("Tạo lịch đầu tiên")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tạo lịch" })).toBeTruthy();
  });

  it("shows_only_the_title_when_that_is_all_it_gets", () => {
    const { container } = render(<EmptyState title="Trống" />);

    expect(container.querySelectorAll("p").length).toBe(1);
  });
});
