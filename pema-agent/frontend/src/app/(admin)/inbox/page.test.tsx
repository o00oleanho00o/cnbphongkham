// @vitest-environment jsdom
// The Inbox with several people at once, against a fake of the typed client and a fake EventSource: a colleague
// shows as "đang xem / đang trả lời" in the list and in the thread (a warning, never a lock), our own presence
// beat is sent, an `inbox.changed` event reloads the right list and thread without losing the selection or the
// draft being typed. The shared-inbox part (tabs, identity filter, Nhận / Tiếp quản / Trả lại, the lock, the
// takeover toast, the role guards) is at the end of the file, against the same fakes.
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
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: api.push, replace: api.replace }),
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
  leavePresence: () => Promise.resolve(),
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

function summary(
  id: string,
  name: string,
  viewers: Viewer[] = [],
  holder: { id: string | null; name: string | null } = { id: null, name: null },
) {
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
    assigned_user_id: holder.id,
    assigned_user_name: holder.name,
    assignment_version: 3,
    viewers,
  };
}

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

let listViewers: Viewer[] = [];
let detailViewers: Viewer[] = [];
let detailAssignee: string | null = null;
let rows: ReturnType<typeof summary>[] | null = null;

function route(path: string, options?: { params?: { path?: { conversation_id?: string } } }) {
  if (path === "/api/v1/conversations") {
    const items = rows ?? [summary(C1, "Khách Một", listViewers), summary(C2, "Khách Hai")];
    return ok({ items, total: items.length, limit: 100, offset: 0 });
  }
  if (path === "/api/v1/identities") return ok(IDENTITIES);
  if (path === "/api/v1/conversations/{conversation_id}") {
    const id = options?.params?.path?.conversation_id ?? C1;
    return ok({
      ...summary(id, "Khách Một", detailViewers),
      assigned_user_id: detailAssignee,
      assigned_user_name: detailAssignee === LAN ? "Bùi Ngọc Lan" : null,
      created_at: "x",
      external_ref: "z",
    });
  }
  if (path === "/api/v1/conversations/{conversation_id}/messages") {
    return ok({ items: [], total: 0, limit: 200, offset: 0 });
  }
  return ok({ items: [], total: 0, limit: 20, offset: 0 });
}

function identity(id: string, label: string, channel: string) {
  return {
    id,
    label,
    channel,
    purpose: "customer",
    enabled: true,
    channel_enabled: true,
    kill_switch_on: false,
    overrides: {},
    effective: { daily_cap: null, send_gap_min_s: 0, send_gap_max_s: 0 },
  };
}

const IDENTITIES = [
  identity("long", "Long", "zalo_oa"),
  identity("bot", "Pema CSKH", "zalo_bot"),
  { ...identity("noi-bo", "Pema Nội bộ", "zalo_personal"), purpose: "internal" },
];

const CAN_CLAIM = ["conversation.read", "conversation.reply", "review.read", "thread.claim"];

function renderInbox(
  permissions: string[] = ["conversation.read", "conversation.reply", "review.read"],
) {
  return render(
    <SessionProvider
      user={{
        id: ME,
        clinic_id: "clinic",
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: "Mai Anh",
        role: "cs_staff",
      }}
      permissions={permissions as never}
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
  rows = null;
  api.replace.mockReset();
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

describe("Inbox queue tabs and identity filter", () => {
  const queued = summary(C1, "Khách Một");
  const mine = summary(C2, "Khách Hai", [], { id: ME, name: "Mai Anh" });
  const theirs = {
    ...summary("00000000-0000-4000-8007-000000000003", "Khách Ba", [], {
      id: LAN,
      name: "Bùi Ngọc Lan",
    }),
    channel: "zalo_bot",
  };

  beforeEach(() => {
    rows = [queued, mine, theirs];
  });

  it("opens_on_the_queue_for_a_role_that_can_claim_and_lists_only_unassigned_threads", async () => {
    renderInbox(CAN_CLAIM);

    expect(await screen.findByText("Khách Một")).toBeTruthy();
    expect(screen.queryByText("Khách Hai")).toBeNull();
    expect(screen.queryByText("Khách Ba")).toBeNull();
  });

  it("counts_each_tab_from_the_loaded_rows", async () => {
    renderInbox(CAN_CLAIM);

    await screen.findByText("Khách Một");

    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual(["Chờ nhận1", "Của tôi1", "Tất cả3"]);
  });

  it("says_who_holds_each_thread_on_the_tab_Tất_cả", async () => {
    api.search.current = "tab=all";
    renderInbox(CAN_CLAIM);

    expect(await screen.findByText(/Bạn đang giữ/)).toBeTruthy();
    expect(screen.getByText(/Bùi Ngọc Lan đang giữ/)).toBeTruthy();
    expect(screen.getByText(/Chưa ai nhận/)).toBeTruthy();
  });

  it("opens_on_Tất_cả_for_a_role_that_only_reads", async () => {
    renderInbox();

    expect(await screen.findByText("Khách Hai")).toBeTruthy();
    expect(screen.getByText("Khách Một")).toBeTruthy();
  });

  it("keeps_the_tab_in_the_url_so_it_survives_a_reload", async () => {
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await screen.findByText("Khách Một");

    await user.click(screen.getByRole("tab", { name: /Của tôi/ }));

    expect(api.replace).toHaveBeenCalledWith("/inbox?tab=mine");
  });

  it("filters_the_loaded_rows_by_identity_and_keeps_the_choice_in_the_url", async () => {
    api.search.current = "tab=all&identity=bot";
    renderInbox(CAN_CLAIM);

    expect(await screen.findByText("Khách Ba")).toBeTruthy();
    expect(screen.queryByText("Khách Một")).toBeNull();

    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Lọc theo danh tính"));
    await user.click(await screen.findByRole("option", { name: "Long" }));
    expect(api.replace).toHaveBeenCalledWith("/inbox?tab=all&identity=long");
  });

  it("offers_the_customer_identities_only_and_not_the_internal_account", async () => {
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await screen.findByText("Khách Một");

    await user.click(screen.getByLabelText("Lọc theo danh tính"));

    const labels = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(labels).toEqual(["Tất cả danh tính", "Long", "Pema CSKH"]);
  });

  it("names_the_queue_when_it_is_empty", async () => {
    rows = [mine];
    renderInbox(CAN_CLAIM);

    expect(await screen.findByText("Không có hội thoại nào đang chờ nhận")).toBeTruthy();
  });
});

describe("Inbox holder actions", () => {
  beforeEach(() => {
    api.search.current = `c=${C1}`;
  });

  it("offers_Nhận_when_nobody_holds_the_thread_and_claims_it_after_the_dialog", async () => {
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Nhận" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Nhận" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    expect(api.post.mock.calls[0]?.[0]).toBe("/api/v1/conversations/{conversation_id}/claim");
  });

  it("locks_the_reply_box_and_offers_Tiếp_quản_while_a_colleague_holds_the_thread", async () => {
    detailAssignee = LAN;
    renderInbox(CAN_CLAIM);

    expect(await screen.findByText("Bùi Ngọc Lan đang trả lời — Tiếp quản?")).toBeTruthy();
    const reply = screen.getByLabelText("Nội dung trả lời") as HTMLTextAreaElement;
    expect(reply.disabled).toBe(true);
    expect(reply.placeholder).toBe("Bùi Ngọc Lan đang phụ trách. Tiếp quản để nhắn khách.");
    expect((screen.getByRole("button", { name: "Gửi" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("needs_a_reason_to_take_over_and_sends_it_with_the_assignment_version", async () => {
    detailAssignee = LAN;
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Tiếp quản" }));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Tiếp quản" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    await user.type(within(dialog).getByLabelText(/Lý do tiếp quản/), "Bác sĩ cần xem ảnh ngay");
    await user.click(confirm);

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const call = api.post.mock.calls[0] as [
      string,
      { body: { reason: string; assignment_version: number } },
    ];
    expect(call[0]).toBe("/api/v1/conversations/{conversation_id}/takeover");
    expect(call[1].body).toEqual({ reason: "Bác sĩ cần xem ảnh ngay", assignment_version: 3 });
  });

  it("offers_Trả_lại_on_my_own_thread_and_releases_it_to_the_queue", async () => {
    detailAssignee = ME;
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    expect(await screen.findByText("Bạn đang phụ trách hội thoại này.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Trả lại" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Trả lại" }));

    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const call = api.post.mock.calls[0] as [string, { body: { to_agent: boolean } }];
    expect(call[0]).toBe("/api/v1/conversations/{conversation_id}/release");
    expect(call[1].body.to_agent).toBe(false);
  });

  it("says_the_care_loop_is_not_connected_when_returning_to_the_assistant_answers_501", async () => {
    detailAssignee = ME;
    api.post.mockImplementation(() =>
      Promise.resolve({
        error: { error: { code: "not_implemented", message: "x" } },
        response: new Response(null, { status: 501 }),
      }),
    );
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Trả lại" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByLabelText(/Trả lại cho trợ lý AI/));
    await user.click(within(dialog).getByRole("button", { name: "Trả lại" }));

    expect(
      await within(dialog).findByText(
        "Chưa nối với trợ lý chăm sóc nên chưa trả lại cho trợ lý được.",
      ),
    ).toBeTruthy();
  });

  it("offers_Giao_cho_only_to_a_role_that_may_assign", async () => {
    renderInbox(CAN_CLAIM);
    await screen.findByRole("button", { name: "Lịch sử phụ trách" });
    expect(screen.queryByRole("button", { name: "Giao cho..." })).toBeNull();
    cleanup();

    renderInbox([...CAN_CLAIM, "thread.assign"]);
    expect(await screen.findByRole("button", { name: "Giao cho..." })).toBeTruthy();
  });

  it("gives_a_read_only_role_one_sentence_and_no_claim_button_or_reply_box", async () => {
    renderInbox(["conversation.read"]);

    expect(
      await screen.findByText(
        "Vai trò của bạn chỉ xem được hội thoại, không nhận hay trả lời được.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Nhận" })).toBeNull();
    expect(screen.queryByLabelText("Nội dung trả lời")).toBeNull();
  });

  it("shows_the_history_of_who_held_the_thread", async () => {
    api.get.mockImplementation((path: string, options?: unknown) =>
      path === "/api/v1/conversations/{conversation_id}/assignments"
        ? ok([
            {
              id: "a1",
              at: "2026-09-20T09:40:00+07:00",
              kind: "takeover",
              by: "Hoàng Nam",
              user_id: ME,
              user_name: "Hoàng Nam",
              previous_user_id: LAN,
              previous_user_name: "Mai Anh",
              reason: "Chị khách cần bác sĩ xem ảnh ngay",
            },
          ])
        : route(path, options as never),
    );
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Lịch sử phụ trách" }));

    expect(await screen.findByText("Hoàng Nam tiếp quản từ Mai Anh")).toBeTruthy();
    expect(screen.getByText("Lý do: Chị khách cần bác sĩ xem ảnh ngay")).toBeTruthy();
  });
});

describe("Inbox when a send is refused", () => {
  function refuseSend(code: string, message: string, status: number) {
    api.post.mockImplementation((path: string) =>
      path === "/api/v1/conversations/{conversation_id}/messages"
        ? Promise.resolve({
            error: { error: { code, message } },
            response: new Response(null, { status }),
          })
        : ok(undefined),
    );
  }

  beforeEach(() => {
    api.search.current = `c=${C1}`;
  });

  it("turns_a_thread_locked_answer_into_the_takeover_banner_and_keeps_the_draft", async () => {
    refuseSend("thread_locked", "Bùi Ngọc Lan đang trả lời — Tiếp quản?", 409);
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nội dung trả lời"), "Dạ em chào chị");

    await user.click(screen.getByRole("button", { name: "Gửi" }));

    expect(await screen.findByText("Tin chưa gửi. Nội dung bạn soạn vẫn còn.")).toBeTruthy();
    expect((screen.getByLabelText("Nội dung trả lời") as HTMLTextAreaElement).value).toBe(
      "Dạ em chào chị",
    );
  });

  it("explains_no_identity_in_words", async () => {
    refuseSend("no_identity", "x", 422);
    renderInbox(CAN_CLAIM);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Nội dung trả lời"), "Dạ em chào chị");

    await user.click(screen.getByRole("button", { name: "Gửi" }));

    expect(await screen.findByText(/chưa gắn với tài khoản Zalo nào/)).toBeTruthy();
  });
});

describe("Inbox takeover notice", () => {
  it("tells_the_previous_holder_when_a_colleague_takes_their_thread_over", async () => {
    rows = [summary(C1, "Khách Một", [], { id: ME, name: "Mai Anh" })];
    api.search.current = "tab=all";
    renderInbox(CAN_CLAIM);
    await screen.findByText("Khách Một");
    stream().open();

    rows = [summary(C1, "Khách Một", [], { id: LAN, name: "Bùi Ngọc Lan" })];
    stream().emit({ type: "assignment.changed", id: C1 });

    expect(
      await screen.findByText(/Đã bị tiếp quản: Bùi Ngọc Lan giữ hội thoại #0000/),
    ).toBeTruthy();
  });
});
