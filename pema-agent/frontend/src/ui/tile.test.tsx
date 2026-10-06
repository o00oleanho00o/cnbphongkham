// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Tile } from "./tile";

afterEach(() => cleanup());

describe("Tile", () => {
  it("shows_label_value_and_note", () => {
    render(<Tile label="Việc quá hạn" value="2" note="Cần xử lý hôm nay" />);

    expect(screen.getByText("Việc quá hạn")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Cần xử lý hôm nay")).toBeTruthy();
  });

  it("colours_only_the_note_so_the_words_still_carry_the_meaning", () => {
    render(<Tile label="Quá hạn" value="2" note="Cần xử lý" tone="danger" />);

    expect(screen.getByText("Cần xử lý").className).toContain("text-danger");
    expect(screen.getByText("2").className).not.toContain("text-danger");
  });

  it("omits_the_note_line_when_there_is_no_note", () => {
    render(<Tile label="Mới" value="5" />);

    expect(screen.queryByText("Cần xử lý")).toBeNull();
    expect(screen.getByText("5").nextElementSibling).toBeNull();
  });
});
