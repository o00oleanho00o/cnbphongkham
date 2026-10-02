// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssigneeStatus } from "@/components/ops/assignee-status";

afterEach(() => cleanup());

describe("AssigneeStatus", () => {
  it("says the list is loading", () => {
    render(<AssigneeStatus loading error="" onRetry={() => undefined} />);
    expect(screen.getByRole("status").textContent).toBe("Đang tải danh sách nhân viên...");
  });

  it("says the list could not be read and retries on request", async () => {
    const retry = vi.fn();
    render(<AssigneeStatus loading={false} error="Lỗi 500" onRetry={retry} />);
    expect(screen.getByRole("status").textContent).toContain("Chưa tải được danh sách nhân viên");

    await userEvent.setup().click(screen.getByRole("button", { name: "Thử lại" }));

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("prefers the error to the loading line while a retry is on its way", () => {
    render(<AssigneeStatus loading error="Lỗi 500" onRetry={() => undefined} />);
    expect(screen.queryByText("Đang tải danh sách nhân viên...")).toBeNull();
  });

  it("renders nothing once the list is there", () => {
    const { container } = render(
      <AssigneeStatus loading={false} error="" onRetry={() => undefined} />,
    );
    expect(container.innerHTML).toBe("");
  });
});
