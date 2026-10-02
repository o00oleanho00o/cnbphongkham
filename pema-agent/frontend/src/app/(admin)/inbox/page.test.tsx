// @vitest-environment jsdom
// The Inbox with several people at once, against a fake of the typed client and a fake EventSource: a colleague
// shows as "đang xem / đang trả lời" in the list and in the thread (a warning, never a lock), our own presence
// beat is sent, an `inbox.changed` event reloads the right list and thread without losing the selection or the
// draft being typed, and the "Phụ trách" box offers Tôi, Giữ nguyên and the assignable staff.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import { COALESCE_MS, FALLBACK_AFTER_MS, POLL_EVERY_MS } from "@/lib/live/live-connection";
import { SessionProvider } from "@/lib/session/session-context";

import InboxPage from "./page";

const ME = "00000000-0000-4000-8000-000000000004";
const LAN = "00000000-0000-4000-8000-000000000007";
const HA = "00000000-0000-4000-8000-000000000001";
const C1 = "00000000-0000-4000-8007-000000000001";
const C2 = "00000000-0000-4000-8007-000000000002";

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  presence: vi.fn(),
  staff: vi.fn(),
  search: { current: "" },
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: api.push }),
  useSearchParams: () => new URLSearchParams(api.search.current),
}));
vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    http: {
      GET: (...args: unknown[]) => api.get(...args),
      POST: (...args: unknown[]) => api.post(...args),
      PATCH: (...args: unknown[]) => api.patch(...args),
    },
  };
});
vi.mock("@/lib/live/live-api", () => ({
  postPresence: (...args: unknown[]) => api.presence(...args),
}));
vi.mock("@/lib/staff/assignable-staff", () => ({
  fetchAssignableStaff: () => api.staff(),
  invalidateAssignableStaff: () => undefined,
}));

class FakeEventSource {
  static all: FakeEventSource[] = [];
  readyState = 0;
  closed = false;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(readonly url: string) {
    FakeEventSource.all.push(this);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  emit(data: unknown): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(data) }));
  }

  drop(): void {
    this.readyState = 0;
    this.onerror?.(new Event("error"));
  }
}

type Viewer = { user_id: string; name: string; state: "viewing" | "replying" };

function summary(id: string, name: string, viewers: Viewer[] = []) {
  return {
    id,
    channel: "zalo_oa",
    status: "open",
    has_pending_review: false,
    last_message_at: "2026-10-02T09:00:00+07:00",
    last_message_preview: `Tin của ${name}`,
    patient_code: "BN-0001",
    patient_display_name: name,
    patient_id: "p-1",
    unread_count: 0,
    version: 1,
    assigned_user_id: null,
    viewers,
  };
}

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

let listViewers: Viewer[] = [];
let detailViewers: Viewer[] = [];
let detailAssignee: string | null = null;

function route(path: string, options?: { params?: { path?: { conversation_id?: string } } }) {
  if (path === "/api/v1/conversations") {
    const items = [summary(C1, "Khách Một", listViewers), summary(C2, "Khách Hai")];
    return ok({ items, total: items.length, limit: 100, offset: 0 });
  }
  if (path === "/api/v1/conversations/{conversation_id}") {
    const id = options?.params?.path?.conversation_id ?? C1;
    return ok({
      ...summary(id, "Khách Một", detailViewers),
      assigned_user_id: detailAssignee,
      created_at: "x",
      external_ref: "z",
    });
  }
  if (path === "/api/v1/conversations/{conversation_id}/messages") {
    return ok({ items: [], total: 0, limit: 200, offset: 0 });
  }
  return ok({ items: [], total: 0, limit: 20, offset: 0 });
}

function renderInbox() {
  return render(
    <SessionProvider
      user={{
        id: ME,
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={["conversation.read", "conversation.reply", "review.read"]}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <InboxPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

function callsTo(path: string, conversationId?: string): number {
  return api.get.mock.calls.filter((call) => {
    const options = call[1] as { params?: { path?: { conversation_id?: string } } } | undefined;
    if (call[0] !== path) return false;
    return (
      conversationId === undefined || options?.params?.path?.conversation_id === conversationId
    );
  }).length;
}

const stream = () => FakeEventSource.all[FakeEventSource.all.length - 1] as FakeEventSource;

beforeEach(() => {
  FakeEventSource.all = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  Element.prototype.scrollIntoView = vi.fn();
  listViewers = [];
  detailViewers = [];
  detailAssignee = null;
  api.search.current = "";
  api.get.mockReset().mockImplementation(route);
  api.post.mockReset().mockImplementation(() => ok(undefined));
  api.patch.mockReset().mockImplementation(() => ok(summary(C1, "Khách Một")));
  api.presence.mockReset().mockResolvedValue(undefined);
  api.staff.mockReset().mockResolvedValue([
    { id: ME, name: "Mai Anh", role: "cs_staff" },
    { id: LAN, name: "Bùi Ngọc Lan", role: "manager" },
    { id: HA, name: "Nguyễn Thanh Hà", role: "owner" },
  ]);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Inbox presence", () => {
  it("shows who is viewing a conversation in the list", async () => {
    listViewers = [{ user_id: LAN, name: "Bùi Ngọc Lan", state: "viewing" }];
    renderInbox();
    expect(await screen.findByText("Lan đang xem")).toBeTruthy();
  });

  it("shows nothing when nobody else is on the conversation", async () => {
    renderInbox();
    await screen.findByText("Khách Một");
    expect(screen.queryByTestId("presence-line")).toBeNull();
  });

  it("shows who is replying in the thread and warns without blocking the reply box", async () => {
    api.search.current = `c=${C1}`;
    listViewers = [{ user_id: HA, name: "Nguyễn Thanh Hà", state: "replying" }];
    detailViewers = listViewers;
    renderInbox();
    const warning = await screen.findByText(/Hà đang trả lời\. Bạn vẫn nhắn được/);
    expect(warning).toBeTruthy();
    const reply = screen.getByLabelText("Nội dung trả lời") as HTMLTextAreaElement;
    expect(reply.disabled).toBe(false);
  });

  it("beats viewing when a conversation is open and replying once there is a draft", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    await waitFor(() => expect(api.presence).toHaveBeenCalledWith(C1, "viewing"));
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nội dung trả lời"), "Dạ chào chị");
    await waitFor(() => expect(api.presence).toHaveBeenLastCalledWith(C1, "replying"));
  });

  it("sends no beat when no conversation is open", async () => {
    renderInbox();
    await screen.findByText("Khách Một");
    expect(api.presence).not.toHaveBeenCalled();
  });
});

describe("Inbox live updates", () => {
  it("opens the event stream of the contract", async () => {
    renderInbox();
    await screen.findByText("Khách Một");
    expect(stream().url).toBe("/api/v1/events");
  });

  it("reloads the list on inbox.changed and keeps the selection and the draft being typed", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const user = userEvent.setup();
    const reply = (await screen.findByLabelText("Nội dung trả lời")) as HTMLTextAreaElement;
    await user.type(reply, "Dạ em chào chị");
    stream().open();
    const listCalls = callsTo("/api/v1/conversations");
    const threadCalls = callsTo("/api/v1/conversations/{conversation_id}", C1);

    stream().emit({ type: "inbox.changed", id: C2 });

    await waitFor(() => expect(callsTo("/api/v1/conversations")).toBe(listCalls + 1));
    expect(callsTo("/api/v1/conversations/{conversation_id}", C1)).toBe(threadCalls);
    expect((screen.getByLabelText("Nội dung trả lời") as HTMLTextAreaElement).value).toBe(
      "Dạ em chào chị",
    );
    expect(screen.getByRole("button", { name: /Khách Một/ }).getAttribute("aria-current")).toBe(
      "true",
    );
  });

  it("also reloads the open thread when the event is about it, still keeping the draft", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nội dung trả lời"), "Dạ em chào chị");
    stream().open();
    const threadCalls = callsTo("/api/v1/conversations/{conversation_id}", C1);

    stream().emit({ type: "inbox.changed", id: C1 });

    await waitFor(() =>
      expect(callsTo("/api/v1/conversations/{conversation_id}", C1)).toBe(threadCalls + 1),
    );
    expect((screen.getByLabelText("Nội dung trả lời") as HTMLTextAreaElement).value).toBe(
      "Dạ em chào chị",
    );
  });

  it("shows a colleague who just opened the conversation, after presence.changed", async () => {
    renderInbox();
    await screen.findByText("Khách Một");
    stream().open();
    expect(screen.queryByText("Lan đang xem")).toBeNull();

    listViewers = [{ user_id: LAN, name: "Bùi Ngọc Lan", state: "viewing" }];
    stream().emit({ type: "presence.changed", id: C1 });

    expect(await screen.findByText("Lan đang xem")).toBeTruthy();
  });

  it("ignores an event type it does not show (tasks)", async () => {
    renderInbox();
    await screen.findByText("Khách Một");
    stream().open();
    const listCalls = callsTo("/api/v1/conversations");
    stream().emit({ type: "tasks.changed", id: "t-1" });
    await new Promise((resolve) => setTimeout(resolve, COALESCE_MS + 100));
    expect(callsTo("/api/v1/conversations")).toBe(listCalls);
  });

  it("falls back to refreshing every 30 seconds when the stream is down for over 10 seconds, and says so", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderInbox();
    await screen.findByText("Khách Một");
    stream().open();
    stream().drop();
    expect(screen.queryByText(/Mất kết nối cập nhật trực tiếp/)).toBeNull();
    const before = callsTo("/api/v1/conversations");

    await vi.advanceTimersByTimeAsync(FALLBACK_AFTER_MS);
    expect(await screen.findByText(/Mất kết nối cập nhật trực tiếp/)).toBeTruthy();
    expect(callsTo("/api/v1/conversations")).toBe(before);
    await vi.advanceTimersByTimeAsync(POLL_EVERY_MS);

    await waitFor(() => expect(callsTo("/api/v1/conversations")).toBe(before + 1));
  });

  it("closes the stream when the page is left", async () => {
    const { unmount } = renderInbox();
    await screen.findByText("Khách Một");
    stream().open();
    unmount();
    expect(stream().closed).toBe(true);
  });
});

describe("Inbox assignment box", () => {
  it("offers Tôi, Giữ nguyên and the assignable staff, and assigns the colleague that is picked", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const user = userEvent.setup();
    const box = await screen.findByLabelText("Phụ trách hội thoại");
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    await user.click(box);
    const options = await screen.findAllByRole("option");
    await waitFor(() =>
      expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
        "Tôi (Mai Anh)",
        "Giữ nguyên: chưa giao",
        "Bùi Ngọc Lan (Quản lý)",
        "Nguyễn Thanh Hà (Chủ phòng khám)",
      ]),
    );
    expect(options.length).toBeGreaterThan(0);

    await user.click(screen.getByRole("option", { name: "Bùi Ngọc Lan (Quản lý)" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const request = api.patch.mock.calls[0]?.[1] as { body: { assigned_user_id: string } };
    expect(request.body.assigned_user_id).toBe(LAN);
  });

  it("changes nothing when Giữ nguyên is picked", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Phụ trách hội thoại"));
    await user.click(await screen.findByRole("option", { name: /Giữ nguyên/ }));
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("offers Chưa giao once somebody owns the conversation and hands it back to nobody", async () => {
    api.search.current = `c=${C1}`;
    detailAssignee = LAN;
    renderInbox();
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Phụ trách hội thoại"));
    await waitFor(() =>
      expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
        "Tôi (Mai Anh)",
        "Giữ nguyên: Bùi Ngọc Lan",
        "Chưa giao",
        "Nguyễn Thanh Hà (Chủ phòng khám)",
      ]),
    );

    await user.click(screen.getByRole("option", { name: "Chưa giao" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const request = api.patch.mock.calls[0]?.[1] as { body: { assigned_user_id: string | null } };
    expect(request.body.assigned_user_id).toBeNull();
  });

  it("can be used with the keyboard alone: Enter opens, arrows move, Enter picks", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const user = userEvent.setup();
    const box = await screen.findByLabelText("Phụ trách hội thoại");
    await waitFor(() => expect(api.staff).toHaveBeenCalled());
    await screen.findByRole("button", { name: "Nhận xử lý" });
    box.focus();

    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByRole("option")).toHaveLength(4));
    await user.keyboard("{ArrowDown}{Enter}");

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const request = api.patch.mock.calls[0]?.[1] as { body: { assigned_user_id: string } };
    expect(request.body.assigned_user_id).toBe(LAN);
    expect(box.getAttribute("aria-haspopup")).toBe("listbox");
  });

  it("keeps working while the colleagues load and says so", async () => {
    api.search.current = `c=${C1}`;
    api.staff.mockReset().mockReturnValue(new Promise(() => undefined));
    renderInbox();
    const user = userEvent.setup();
    expect(await screen.findByText("Đang tải danh sách nhân viên...")).toBeTruthy();
    await user.click(await screen.findByLabelText("Phụ trách hội thoại"));
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Tôi (Mai Anh)",
      "Giữ nguyên: chưa giao",
    ]);
  });

  it("says when the colleagues cannot be read and offers Thử lại, which reads them again", async () => {
    api.search.current = `c=${C1}`;
    api.staff.mockReset().mockRejectedValueOnce(new Error("Lỗi 500"));
    api.staff.mockResolvedValue([{ id: LAN, name: "Bùi Ngọc Lan", role: "manager" }]);
    renderInbox();
    const user = userEvent.setup();
    expect(await screen.findByText(/Chưa tải được danh sách nhân viên/)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    await waitFor(() => expect(screen.queryByText(/Chưa tải được danh sách nhân viên/)).toBeNull());
    await user.click(screen.getByLabelText("Phụ trách hội thoại"));
    expect(await screen.findByRole("option", { name: "Bùi Ngọc Lan (Quản lý)" })).toBeTruthy();
    expect(api.staff).toHaveBeenCalledTimes(2);
  });

  it("keeps the Nhận xử lý button working: it assigns the conversation to me", async () => {
    api.search.current = `c=${C1}`;
    detailAssignee = LAN;
    renderInbox();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nhận xử lý" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalled());
    const request = api.patch.mock.calls[0]?.[1] as { body: { assigned_user_id: string } };
    expect(request.body.assigned_user_id).toBe(ME);
  });

  it("lives in the thread header next to the status box", async () => {
    api.search.current = `c=${C1}`;
    renderInbox();
    const header = (await screen.findByLabelText("Phụ trách hội thoại")).closest("header");
    expect(header).not.toBeNull();
    expect(within(header as HTMLElement).getByLabelText("Trạng thái hội thoại")).toBeTruthy();
  });
});
