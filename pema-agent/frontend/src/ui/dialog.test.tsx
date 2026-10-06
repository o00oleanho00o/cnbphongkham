// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { Dialog, Sheet, wrapFocusTarget } from "./dialog";

afterEach(() => cleanup());

/** Hand-written spy: counts how often the dialog asked to be closed. */
function closeSpy(): { closed: number; close: () => void } {
  const state = {
    closed: 0,
    close: () => {
      state.closed += 1;
    },
  };
  return state;
}

const noop = (): void => undefined;

describe("Dialog", () => {
  it("is_a_modal_dialog_named_by_its_title", () => {
    render(
      <Dialog title="Xác nhận" onClose={noop}>
        nội dung
      </Dialog>,
    );

    expect(screen.getByRole("dialog", { name: "Xác nhận" }).getAttribute("aria-modal")).toBe(
      "true",
    );
  });

  it("closes_on_escape", async () => {
    const spy = closeSpy();
    render(
      <Dialog title="Xác nhận" onClose={spy.close}>
        nội dung
      </Dialog>,
    );

    await userEvent.setup().keyboard("{Escape}");

    expect(spy.closed).toBe(1);
  });

  it("closes_from_the_close_button", async () => {
    const spy = closeSpy();
    render(
      <Dialog title="Xác nhận" onClose={spy.close}>
        nội dung
      </Dialog>,
    );

    await userEvent.setup().click(screen.getByRole("button", { name: "Đóng" }));

    expect(spy.closed).toBe(1);
  });

  it("closes_when_press_and_release_both_land_on_the_backdrop", () => {
    const spy = closeSpy();
    render(
      <Dialog title="Xác nhận" onClose={spy.close}>
        nội dung
      </Dialog>,
    );
    const backdrop = screen.getByRole("dialog");

    fireEvent.pointerDown(backdrop);
    fireEvent.click(backdrop);

    expect(spy.closed).toBe(1);
  });

  it("does_not_close_when_a_drag_starts_inside_and_ends_on_the_backdrop", () => {
    const spy = closeSpy();
    render(
      <Dialog title="Xác nhận" onClose={spy.close}>
        <textarea aria-label="Ghi chú" />
      </Dialog>,
    );
    const backdrop = screen.getByRole("dialog");

    fireEvent.pointerDown(screen.getByLabelText("Ghi chú"));
    fireEvent.click(backdrop);

    expect(spy.closed).toBe(0);
  });

  it("moves_focus_into_the_dialog_on_open", () => {
    render(
      <Dialog title="Xác nhận" onClose={noop}>
        nội dung
      </Dialog>,
    );

    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("keeps_tab_inside_the_dialog", async () => {
    render(
      <Dialog title="Xác nhận" onClose={noop} footer={<button>Lưu</button>}>
        <input aria-label="Tên" />
      </Dialog>,
    );
    screen.getByRole("button", { name: "Lưu" }).focus();

    await userEvent.setup().tab();

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Đóng" }));
  });

  it("returns_focus_to_the_opener_when_it_closes", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = render(
      <Dialog title="Xác nhận" onClose={noop}>
        nội dung
      </Dialog>,
    );

    unmount();

    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});

describe("Sheet", () => {
  it("slides_up_from_the_bottom_on_a_phone", () => {
    render(
      <Sheet title="Sửa lịch" onClose={noop}>
        nội dung
      </Sheet>,
    );

    expect(screen.getByRole("dialog").className).toContain("items-end");
  });
});

describe("wrapFocusTarget", () => {
  const [first, second, last] = ["a", "b", "c"].map(() => document.createElement("button"));
  const all = [first, second, last] as HTMLElement[];

  it("goes_from_the_last_element_to_the_first_on_tab", () => {
    expect(wrapFocusTarget(all, last as HTMLElement, false)).toBe(first);
  });

  it("goes_from_the_first_element_to_the_last_on_shift_tab", () => {
    expect(wrapFocusTarget(all, first as HTMLElement, true)).toBe(last);
  });

  it("lets_the_browser_move_between_inner_elements", () => {
    expect(wrapFocusTarget(all, second as HTMLElement, false)).toBeNull();
  });

  it("pulls_focus_back_in_when_it_is_outside", () => {
    expect(wrapFocusTarget(all, document.body, false)).toBe(first);
  });

  it("does_nothing_when_nothing_can_take_focus", () => {
    expect(wrapFocusTarget([], null, false)).toBeNull();
  });
});
