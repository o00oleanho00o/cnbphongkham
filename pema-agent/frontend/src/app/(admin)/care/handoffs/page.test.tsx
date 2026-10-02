// @vitest-environment jsdom
// "Yêu cầu đang chờ tôi" against a fake of the care API and a fake EventSource: the list shows what the backend
// says (reason, summary, SLA, the buttons it allows), Nhận goes to the timeline, Từ chối needs a reason and
// sends the suggestion, a `handoff.changed` event reloads the list quietly, and a role without `care.read` gets
// a plain "no access" note and no request.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import HandoffsPage from "./page";

const ME = "00000000-0000-4000-8000-000000000004";
const P1 = "00000000-0000-4000-8002-000000000002";
const P2 = "00000000-0000-4000-8002-000000000003";
const COLLEAGUE = "00000000-0000-4000-8000-000000000006";

const api = vi.hoisted(() => ({
  handoffs: vi.fn(),
  accept: vi.fn(),
  decline: vi.fn(),
  staff: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: api.push }) }));
vi.mock("@/lib/care/care-api", () => ({
  careApi: {
    handoffs: (...args: unknown[]) => api.handoffs(...args),
    accept: (...args: unknown[]) => api.accept(...args),
    decline: (...args: unknown[]) => api.decline(...args),
  },
}));
vi.mock("@/lib/staff/assignable-staff", () => ({
  fetchAssignableStaff: () => api.staff(),
  invalidateAssignableStaff: () => undefined,
}));

class FakeEventSource {
  static all: FakeEventSource[] = [];
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }
  close(): void {
    this.readyState = 2;
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }
  emit(data: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }
}

function item(patientId: string, name: string, over: Record<string, unknown> = {}) {
  return {
    patient_id: patientId,
    patient_name: name,
    reason: "asks_for_human",
    summary: `Tóm tắt của ${name}`,
    depth: "D2",
    urgency: "normal",
    confidence: 0.72,
    required_skill: "dat_lich",
    opened_at: new Date(Date.now() - 6 * 60_000).toISOString(),
    sla_due_at: new Date(Date.now() + 24 * 60_000).toISOString(),
    position: 1,
    chain_length: 3,
    on_call_step: false,
    suggested_by_name: null,
    mine: true,
    can_accept: true,
    can_decline: true,
    ...over,
  };
}

function renderPage(permissions: Permission[] = ["care.read", "care.act"]) {
  return render(
    <SessionProvider
      user={{
        id: ME,
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <HandoffsPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1] as FakeEventSource;

beforeEach(() => {
  FakeEventSource.all = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  Element.prototype.scrollIntoView = vi.fn();
  api.handoffs.mockReset().mockResolvedValue({
    items: [
      item(P1, "Khách Một"),
      item(P2, "Khách Hai", { urgency: "urgent", depth: "D5", reason: "red_flag" }),
    ],
  });
  api.accept.mockReset().mockResolvedValue({ patient_id: P1, state: "STAFF", outcome: "accepted" });
  api.decline
    .mockReset()
    .mockResolvedValue({ patient_id: P1, state: "HANDOFF_ROUTING", outcome: null });
  api.staff.mockReset().mockResolvedValue([
    { id: ME, name: "Mai Anh", role: "cs_staff" },
    { id: COLLEAGUE, name: "Đặng Minh Thư", role: "cs_staff" },
  ]);
  api.push.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Handoffs page", () => {
  it("shows the reason, the summary and the SLA as the backend sent them", async () => {
    renderPage();
    const card = await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    expect(within(card).getByText("Khách muốn gặp người")).toBeTruthy();
    expect(within(card).getByText("Tóm tắt của Khách Một")).toBeTruthy();
    expect(within(card).getByText(/Còn 2\d phút/)).toBeTruthy();
    expect(within(card).getByText(/bước 1\/3/)).toBeTruthy();
    const urgent = screen.getByRole("article", { name: "Yêu cầu của Khách Hai" });
    expect(within(urgent).getByText("Dấu hiệu nguy hiểm (cờ đỏ)")).toBeTruthy();
    expect(api.handoffs).toHaveBeenCalledWith("mine", expect.anything());
  });

  it("offers only the buttons the backend allows", async () => {
    api.handoffs.mockResolvedValue({
      items: [item(P1, "Khách Một", { mine: false, can_accept: true, can_decline: false })],
    });
    renderPage();
    const card = await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    expect(within(card).getByRole("button", { name: "Nhận cuộc trò chuyện" })).toBeTruthy();
    expect(within(card).queryByRole("button", { name: "Từ chối" })).toBeNull();
  });

  it("opens the timeline after Nhận", async () => {
    renderPage();
    const card = await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    await userEvent
      .setup()
      .click(within(card).getByRole("button", { name: "Nhận cuộc trò chuyện" }));
    await waitFor(() => expect(api.accept).toHaveBeenCalledWith(P1));
    expect(api.push).toHaveBeenCalledWith(`/care/patients/${P1}/timeline`);
  });

  it("shows the refusal of the backend on the card and reloads when somebody was faster", async () => {
    api.accept.mockRejectedValue(new Error("Yêu cầu này đã có người nhận hoặc đã đóng."));
    renderPage();
    const card = await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    const before = api.handoffs.mock.calls.length;
    await userEvent
      .setup()
      .click(within(card).getByRole("button", { name: "Nhận cuộc trò chuyện" }));
    expect(await within(card).findByRole("alert")).toBeTruthy();
    expect(within(card).getByText(/đã có người nhận/)).toBeTruthy();
    await waitFor(() => expect(api.handoffs.mock.calls.length).toBeGreaterThan(before));
    expect(api.push).not.toHaveBeenCalled();
  });

  it("needs a reason to decline, and sends the colleague that was suggested", async () => {
    renderPage();
    const user = userEvent.setup();
    const card = await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    await user.click(within(card).getByRole("button", { name: "Từ chối" }));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Gửi từ chối" }));
    expect(within(dialog).getByText("Hãy ghi lý do từ chối.")).toBeTruthy();
    expect(api.decline).not.toHaveBeenCalled();

    await user.type(within(dialog).getByLabelText("Lý do"), "Đang bận ca khác");
    await user.click(within(dialog).getByLabelText("Gợi ý đồng nghiệp nhận thay"));
    await user.click(await screen.findByRole("option", { name: /Đặng Minh Thư/ }));
    await user.click(within(dialog).getByRole("button", { name: "Gửi từ chối" }));

    await waitFor(() =>
      expect(api.decline).toHaveBeenCalledWith(P1, "Đang bận ca khác", COLLEAGUE),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("reloads quietly on handoff.changed and keeps the list on screen meanwhile", async () => {
    renderPage();
    await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    stream().open();
    const before = api.handoffs.mock.calls.length;
    api.handoffs.mockResolvedValue({ items: [item(P2, "Khách Hai")] });

    stream().emit({ type: "handoff.changed", id: P1 });

    await waitFor(() => expect(api.handoffs.mock.calls.length).toBe(before + 1));
    await waitFor(() =>
      expect(screen.queryByRole("article", { name: "Yêu cầu của Khách Một" })).toBeNull(),
    );
    expect(screen.getByRole("article", { name: "Yêu cầu của Khách Hai" })).toBeTruthy();
    expect(stream().url).toBe("/api/v1/events");
  });

  it("makes no request for a role without care.read", () => {
    renderPage(["conversation.read"]);
    expect(screen.getByText(/không có quyền xem các yêu cầu chuyển giao/)).toBeTruthy();
    expect(api.handoffs).not.toHaveBeenCalled();
    expect(FakeEventSource.all).toHaveLength(0);
  });

  it("asks for all open rounds when the chip is switched", async () => {
    renderPage();
    await screen.findByRole("article", { name: "Yêu cầu của Khách Một" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Tất cả đang mở" }));
    await waitFor(() => expect(api.handoffs).toHaveBeenLastCalledWith("all", expect.anything()));
  });
});
