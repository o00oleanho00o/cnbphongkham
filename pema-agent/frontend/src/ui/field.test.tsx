// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Field } from "./field";

afterEach(() => cleanup());

describe("Field", () => {
  it("labels_the_control_it_wraps", () => {
    render(<Field label="Họ và tên">{(control) => <input {...control} />}</Field>);

    expect(screen.getByLabelText("Họ và tên")).toBeTruthy();
  });

  it("describes_the_control_with_its_hint", () => {
    render(
      <Field label="Họ và tên" hint="Như trên hồ sơ">
        {(control) => <input {...control} />}
      </Field>,
    );

    expect(screen.getByLabelText("Họ và tên").getAttribute("aria-describedby")).toBe(
      screen.getByText("Như trên hồ sơ").id,
    );
  });

  it("announces_an_error_and_marks_the_control_invalid", () => {
    render(
      <Field label="Số điện thoại" error="Chưa đúng định dạng">
        {(control) => <input {...control} />}
      </Field>,
    );

    expect(screen.getByRole("alert").textContent).toBe("Chưa đúng định dạng");
    expect(screen.getByLabelText("Số điện thoại").getAttribute("aria-invalid")).toBe("true");
  });

  it("is_valid_and_undescribed_without_hint_or_error", () => {
    render(<Field label="Ghi chú">{(control) => <textarea {...control} />}</Field>);

    const control = screen.getByLabelText("Ghi chú");
    expect(control.getAttribute("aria-invalid")).toBeNull();
    expect(control.getAttribute("aria-describedby")).toBeNull();
  });
});
