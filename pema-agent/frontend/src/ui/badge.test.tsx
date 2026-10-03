// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Badge } from "./badge";

afterEach(() => cleanup());

describe("Badge", () => {
  it("uses_the_status_tokens_of_its_tone", () => {
    render(<Badge tone="success">Đã xác nhận</Badge>);

    const className = screen.getByText("Đã xác nhận").className;
    expect(className).toContain("bg-success-soft");
    expect(className).toContain("text-success");
  });

  it("defaults_to_the_neutral_tone", () => {
    render(<Badge>Nháp</Badge>);

    expect(screen.getByText("Nháp").className).toContain("bg-tile");
  });

  it("hides_the_status_dot_from_assistive_technology", () => {
    const { container } = render(<Badge tone="danger">Quá hạn</Badge>);

    expect(container.querySelector("[aria-hidden]")).not.toBeNull();
  });

  it("can_drop_the_dot", () => {
    const { container } = render(<Badge dot={false}>Nháp</Badge>);

    expect(container.querySelector("[aria-hidden]")).toBeNull();
  });
});
