// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Button, buttonClass } from "./button";

afterEach(() => cleanup());

describe("Button", () => {
  it("is_a_primary_button_that_does_not_submit_by_default", () => {
    render(<Button>Lưu</Button>);

    const button = screen.getByRole("button", { name: "Lưu" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.className).toContain("bg-brand-500");
  });

  it("uses_the_status_tokens_for_the_danger_variants", () => {
    render(
      <>
        <Button variant="danger">Xóa</Button>
        <Button variant="danger-solid">Xóa hẳn</Button>
      </>,
    );

    expect(screen.getByText("Xóa").className).toContain("text-danger");
    expect(screen.getByText("Xóa hẳn").className).toContain("bg-danger");
  });

  it("can_be_disabled_and_still_takes_extra_classes", () => {
    render(
      <Button variant="secondary" disabled className="w-full">
        Hủy
      </Button>,
    );

    const button = screen.getByRole("button", { name: "Hủy" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.className).toContain("w-full");
  });

  it("gives_the_same_look_to_a_link_through_buttonclass", () => {
    expect(buttonClass("secondary")).toContain("border-line-strong");
  });
});
