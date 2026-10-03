// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { TabPanel, Tabs, targetTabIndex } from "./tabs";

afterEach(() => cleanup());

const ITEMS = [
  { id: "overview", label: "Tổng quan" },
  { id: "consult", label: "Khám", count: 2 },
  { id: "plan", label: "Liệu trình" },
];

function Harness() {
  const [value, setValue] = useState("overview");
  return (
    <>
      <Tabs label="Hồ sơ" idPrefix="t" items={ITEMS} value={value} onChange={setValue} />
      {ITEMS.map((item) => (
        <TabPanel key={item.id} idPrefix="t" id={item.id} value={value}>
          nội dung {item.id}
        </TabPanel>
      ))}
    </>
  );
}

describe("Tabs", () => {
  it("selects_the_first_tab_and_shows_only_its_panel", () => {
    render(<Harness />);

    expect(screen.getByRole("tab", { name: "Tổng quan" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    expect(screen.getByRole("tabpanel").textContent).toBe("nội dung overview");
  });

  it("switches_panel_when_a_tab_is_clicked", async () => {
    render(<Harness />);

    await userEvent.setup().click(screen.getByRole("tab", { name: /Khám/ }));

    expect(screen.getByRole("tabpanel").textContent).toBe("nội dung consult");
  });

  it("moves_to_the_next_tab_with_the_right_arrow_and_focuses_it", async () => {
    render(<Harness />);
    screen.getByRole("tab", { name: "Tổng quan" }).focus();

    await userEvent.setup().keyboard("{ArrowRight}");

    expect(document.activeElement).toBe(screen.getByRole("tab", { name: /Khám/ }));
    expect(screen.getByRole("tabpanel").textContent).toBe("nội dung consult");
  });

  it("wraps_from_the_first_tab_to_the_last_with_the_left_arrow", async () => {
    render(<Harness />);
    screen.getByRole("tab", { name: "Tổng quan" }).focus();

    await userEvent.setup().keyboard("{ArrowLeft}");

    expect(screen.getByRole("tabpanel").textContent).toBe("nội dung plan");
  });

  it("keeps_only_the_selected_tab_in_the_tab_order", () => {
    render(<Harness />);

    const tabIndexes = screen.getAllByRole("tab").map((tab) => tab.getAttribute("tabindex"));
    expect(tabIndexes).toEqual(["0", "-1", "-1"]);
  });

  it("links_each_tab_to_its_panel", () => {
    render(<Harness />);

    const tab = screen.getByRole("tab", { name: "Tổng quan" });
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(tab.id);
    expect(tab.getAttribute("aria-controls")).toBe(screen.getByRole("tabpanel").id);
  });
});

describe("Tabs segmentedOnPhone", () => {
  const WITH_SHORT = [
    { id: "overview", label: "Tổng quan", shortLabel: "Tổng quan" },
    { id: "session", label: "Buổi điều trị", shortLabel: "Buổi" },
  ];

  it("shows_the_short_label_for_the_phone_and_the_full_one_from_lg", () => {
    render(
      <Tabs
        label="Hồ sơ"
        idPrefix="s"
        items={WITH_SHORT}
        value="overview"
        onChange={() => undefined}
        segmentedOnPhone
      />,
    );

    const tab = screen.getByRole("tab", { name: /Buổi/ });
    const spans = tab.querySelectorAll("span");
    expect(spans[0]?.textContent).toBe("Buổi");
    expect(spans[0]?.className).toContain("lg:hidden");
    expect(spans[1]?.textContent).toBe("Buổi điều trị");
    expect(spans[1]?.className).toContain("hidden");
  });

  it("keeps_one_equal_column_per_tab", () => {
    render(
      <Tabs
        label="Hồ sơ"
        idPrefix="s"
        items={WITH_SHORT}
        value="overview"
        onChange={() => undefined}
        segmentedOnPhone
      />,
    );

    expect(screen.getByRole("tablist").style.gridTemplateColumns).toBe("repeat(2, minmax(0, 1fr))");
  });

  it("leaves_the_default_bar_without_a_grid", () => {
    render(<Harness />);

    expect(screen.getByRole("tablist").style.gridTemplateColumns).toBe("");
  });
});

describe("targetTabIndex", () => {
  it.each([
    ["Home", 2, 0],
    ["End", 0, 2],
    ["ArrowRight", 2, 0],
    ["ArrowLeft", 0, 2],
  ])("%s_from_tab_%i_goes_to_tab_%i", (key, from, to) => {
    expect(targetTabIndex(key, from, 3)).toBe(to);
  });

  it("ignores_other_keys", () => {
    expect(targetTabIndex("a", 0, 3)).toBeNull();
  });
});
