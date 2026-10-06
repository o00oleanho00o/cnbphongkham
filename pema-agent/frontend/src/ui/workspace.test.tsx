// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PageHeading, Workspace } from "./workspace";

afterEach(() => cleanup());

describe("Workspace", () => {
  it("is_one_column_without_an_aside", () => {
    const { container } = render(<Workspace>chính</Workspace>);

    expect(container.firstElementChild?.className).not.toContain("xl:grid-cols");
    expect(container.querySelector("aside")).toBeNull();
  });

  it("splits_into_two_columns_from_1280px_when_it_has_an_aside", () => {
    const { container } = render(<Workspace aside={<p>phụ</p>}>chính</Workspace>);

    expect(container.firstElementChild?.className).toContain("xl:grid-cols-[minmax(0,1.8fr)");
    expect(container.querySelector("aside")?.textContent).toBe("phụ");
  });

  it("grows_the_card_grid_to_four_columns_from_1600px", () => {
    const { container } = render(<Workspace layout="cards">thẻ</Workspace>);

    const className = container.firstElementChild?.className ?? "";
    expect(className).toContain("sm:grid-cols-2");
    expect(className).toContain("xl:grid-cols-3");
    expect(className).toContain("wide:grid-cols-4");
  });
});

describe("PageHeading", () => {
  it("shows_the_title_as_the_page_heading_with_its_actions", () => {
    render(
      <PageHeading
        title="Điều phối lịch"
        subtitle="Theo ngày"
        actions={<button>Thêm lịch</button>}
      />,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Điều phối lịch" })).toBeTruthy();
    expect(screen.getByText("Theo ngày")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thêm lịch" })).toBeTruthy();
  });
});
