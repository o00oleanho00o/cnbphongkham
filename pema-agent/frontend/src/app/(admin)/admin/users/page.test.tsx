// @vitest-environment jsdom
// The staff screen (`/admin/users`) against a fake of the typed client: what each role SEES (the owner has every
// button except on their own account, the manager only reads), the filters it sends, the lock confirmation that
// says the person is signed out, the two-password forms, and the Vietnamese sentence for 409/422/429. The
// backend rules themselves are tested in `backend/apps/api/tests/api/test_admin_users_routes.py`.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { SessionProvider, type Permission } from "@/lib/session/session-context";

import StaffPage from "./page";

// The typed HTTP client is the boundary to an unmanaged dependency (the backend API), so it is replaced by a
// fake whose answers each test sets; the screen's own logic runs for real.
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }));

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

type Staff = Schemas["StaffUserOut"];

const OWNER_ID = "00000000-0000-4000-8000-000000000001";
const CLINIC_ID = "00000000-0000-4000-8000-0000000000aa";

function staff(overrides: Partial<Staff> & Pick<Staff, "id" | "display_name">): Staff {
  return {
    email: `${overrides.id}@pema.test`,
    role: "cs_staff",
    active: true,
    last_login_at: null,
    created_at: "2026-08-01T09:00:00+07:00",
    version: 1,
    ...overrides,
  };
}

const ME = staff({ id: OWNER_ID, display_name: "Nguyễn Thanh Hà", role: "owner" });
const MAI = staff({
  id: "u-mai",
  display_name: "Mai Anh",
  last_login_at: "2026-09-30T08:30:00+07:00",
});
const LAN = staff({
  id: "u-lan",
  display_name: "Bùi Ngọc Lan",
  role: "reception",
  active: false,
  version: 2,
});
const ALL_STAFF = [ME, MAI, LAN];

const OWNER_PERMISSIONS: Permission[] = ["admin.users.read", "admin.users"];
const MANAGER_PERMISSIONS: Permission[] = ["admin.users.read"];

function page(items: Staff[]): Schemas["Page_StaffUserOut_"] {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function ok<T>(data: T) {
  return Promise.resolve({ data, response: new Response(null, { status: 200 }) });
}

function refused(status: number, code: string, message: string) {
  return Promise.resolve({
    error: { error: { code, message } },
    response: new Response(null, { status }),
  });
}

function renderPage(permissions: Permission[], role: Schemas["Role"] = "owner") {
  return render(
    <SessionProvider
      user={{
        id: OWNER_ID,
        clinic_id: CLINIC_ID,
        clinic_name: "Phòng khám Pema (dữ liệu mẫu)",
        display_name: ME.display_name,
        role,
      }}
      permissions={permissions}
      onLoggedOut={() => undefined}
    >
      <ToastProvider>
        <StaffPage />
      </ToastProvider>
    </SessionProvider>,
  );
}

function lastListQuery(): Record<string, unknown> {
  const calls = api.get.mock.calls;
  const options = calls[calls.length - 1]?.[1] as { params: { query: Record<string, unknown> } };
  return options.params.query;
}

/** The table and the cards both render in jsdom (CSS hides one); the cards are the phone layout. */
function cards() {
  return within(screen.getByTestId("staff-cards"));
}

/** The first load has finished: the list is on screen. */
async function ready() {
  await screen.findByTestId("staff-cards");
}

beforeEach(() => {
  api.get.mockReset().mockImplementation(() => ok(page(ALL_STAFF)));
  api.post.mockReset().mockImplementation(() => ok(undefined));
  api.patch.mockReset().mockImplementation(() => ok(ME));
});

afterEach(cleanup);

describe("StaffPage as the owner", () => {
  it("lists_every_member_with_role_status_and_last_sign_in", async () => {
    renderPage(OWNER_PERMISSIONS);

    await ready();
    expect(cards().getByText("Mai Anh")).toBeTruthy();
    expect(cards().getByText("Bùi Ngọc Lan")).toBeTruthy();
    expect(cards().getAllByText("Đang hoạt động").length).toBe(2);
    expect(cards().getByText("Đã khóa")).toBeTruthy();
    expect(cards().getAllByText(/Chưa đăng nhập lần nào/).length).toBe(2);
    expect(cards().getByText(/Đăng nhập cuối 30\/09/)).toBeTruthy();
    expect(screen.queryByText(/hash|password_hash/i)).toBeNull();
  });

  it("shows_add_edit_reset_and_lock_on_other_people", async () => {
    renderPage(OWNER_PERMISSIONS);
    await ready();

    expect(screen.getByRole("button", { name: "Thêm nhân viên" })).toBeTruthy();
    expect(cards().getByRole("button", { name: "Sửa Mai Anh" })).toBeTruthy();
    expect(cards().getByRole("button", { name: "Đặt lại mật khẩu của Mai Anh" })).toBeTruthy();
    expect(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" })).toBeTruthy();
    expect(
      cards().getByRole("button", { name: "Mở khóa tài khoản của Bùi Ngọc Lan" }),
    ).toBeTruthy();
  });

  it("hides_lock_and_reset_on_the_own_account_but_keeps_edit", async () => {
    renderPage(OWNER_PERMISSIONS);
    await ready();

    expect(cards().getByRole("button", { name: "Sửa Nguyễn Thanh Hà" })).toBeTruthy();
    expect(
      cards().queryByRole("button", { name: /Khóa tài khoản của Nguyễn Thanh Hà/ }),
    ).toBeNull();
    expect(
      cards().queryByRole("button", { name: /Đặt lại mật khẩu của Nguyễn Thanh Hà/ }),
    ).toBeNull();
    expect(cards().getByText("(Bạn)")).toBeTruthy();
  });

  it("sends_the_search_role_and_status_filters_to_the_list", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(screen.getByRole("button", { name: "Bác sĩ" }));
    await waitFor(() => expect(lastListQuery().role).toBe("doctor"));
    await user.click(screen.getByRole("button", { name: "Đã khóa" }));
    await waitFor(() => expect(lastListQuery().active).toBe(false));
    await user.type(screen.getByLabelText("Tìm nhân viên"), "mai");
    await waitFor(() => expect(lastListQuery().q).toBe("mai"));
    expect(lastListQuery()).toMatchObject({ role: "doctor", active: false, offset: 0 });
  });

  it("says_when_there_is_no_member_and_when_no_member_matches_the_filters", async () => {
    api.get.mockImplementation(() => ok(page([])));
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);

    expect(await screen.findByText("Chưa có nhân viên nào")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Bác sĩ" }));
    expect(await screen.findByText("Không có nhân viên phù hợp")).toBeTruthy();
  });
});

describe("StaffPage as the manager", () => {
  it("lists_but_shows_no_button_that_changes_anything", async () => {
    renderPage(MANAGER_PERMISSIONS, "manager");

    await ready();
    expect(cards().getByText("Mai Anh")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Thêm nhân viên" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Sửa / })).toBeNull();
    expect(screen.queryByRole("button", { name: /Đặt lại mật khẩu/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Khóa|Mở khóa/ })).toBeNull();
    expect(screen.getByText(/Bạn chỉ xem được danh sách/)).toBeTruthy();
  });
});

describe("StaffPage without the read permission", () => {
  it("asks_nothing_and_says_it_is_not_allowed", async () => {
    renderPage([], "cs_staff");

    expect(await screen.findByText("Bạn không có quyền xem danh sách nhân viên")).toBeTruthy();
    expect(api.get).not.toHaveBeenCalled();
  });
});

describe("locking a member", () => {
  it("asks_first_and_says_the_person_is_signed_out", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Khóa tài khoản của Mai Anh\?/)).toBeTruthy();
    expect(within(dialog).getByText(/bị đăng xuất khỏi mọi thiết bị ngay/)).toBeTruthy();
    expect(api.patch).not.toHaveBeenCalled();
  });

  it("sends_the_lock_with_the_version_after_the_owner_confirms_and_reloads", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();
    const listCalls = api.get.mock.calls.length;

    await user.click(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Khóa tài khoản" }),
    );

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0]?.[1]).toMatchObject({
      params: { path: { user_id: "u-mai" } },
      body: { version: 1, active: false },
    });
    expect(await screen.findByText(/Đã khóa tài khoản của Mai Anh/)).toBeTruthy();
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(listCalls));
  });

  it("changes_nothing_when_the_owner_cancels", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Hủy" }),
    );

    expect(api.patch).not.toHaveBeenCalled();
  });

  it("unlocks_a_locked_member", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Mở khóa tài khoản của Bùi Ngọc Lan" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Mở khóa" }),
    );

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0]?.[1]).toMatchObject({ body: { version: 2, active: true } });
  });

  it("shows_the_backend_sentence_when_the_last_owner_would_be_locked", async () => {
    api.patch.mockImplementation(() =>
      refused(
        422,
        "validation_failed",
        "Phòng khám phải luôn có ít nhất một chủ phòng khám đang hoạt động.",
      ),
    );
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Khóa tài khoản" }),
    );

    expect(await screen.findByText(/ít nhất một chủ phòng khám đang hoạt động/)).toBeTruthy();
  });

  it("reloads_the_list_after_a_stale_version", async () => {
    api.patch.mockImplementation(() => refused(409, "version_conflict", "Bản ghi đã đổi."));
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();
    const listCalls = api.get.mock.calls.length;

    await user.click(cards().getByRole("button", { name: "Khóa tài khoản của Mai Anh" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Khóa tài khoản" }),
    );

    expect(await screen.findByText(/vừa được người khác thay đổi/)).toBeTruthy();
    await waitFor(() => expect(api.get.mock.calls.length).toBeGreaterThan(listCalls));
  });
});

describe("adding a member", () => {
  async function openAdd() {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();
    await user.click(screen.getByRole("button", { name: "Thêm nhân viên" }));
    const dialog = await screen.findByRole("dialog");
    return { user, dialog };
  }

  async function fillForm(
    user: ReturnType<typeof userEvent.setup>,
    dialog: HTMLElement,
    again = "mat-khau-moi-1",
  ) {
    await user.type(within(dialog).getByLabelText("Họ tên"), "Trần Bảo Ngọc");
    await user.type(within(dialog).getByLabelText("Email đăng nhập"), "ngoc@pema.test");
    await user.type(within(dialog).getByLabelText("Mật khẩu ban đầu"), "mat-khau-moi-1");
    await user.type(within(dialog).getByLabelText("Nhập lại mật khẩu"), again);
  }

  it("refuses_two_different_passwords_without_calling_the_backend", async () => {
    const { user, dialog } = await openAdd();
    await fillForm(user, dialog, "mat-khau-khac-2");

    await user.click(within(dialog).getByRole("button", { name: "Thêm nhân viên" }));

    expect(await within(dialog).findByText("Hai ô mật khẩu chưa giống nhau.")).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("creates_the_member_and_closes_the_form", async () => {
    const { user, dialog } = await openAdd();
    await fillForm(user, dialog);

    await user.click(within(dialog).getByRole("button", { name: "Thêm nhân viên" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0]?.[0]).toBe("/api/v1/admin/users");
    expect(api.post.mock.calls[0]?.[1]).toMatchObject({
      body: {
        display_name: "Trần Bảo Ngọc",
        email: "ngoc@pema.test",
        role: "cs_staff",
        password: "mat-khau-moi-1",
      },
    });
    expect(await screen.findByText("Đã thêm nhân viên.")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("shows_the_taken_email_sentence_on_a_409_and_keeps_the_form_open", async () => {
    api.post.mockImplementation(() =>
      refused(
        409,
        "invalid_state",
        "Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác.",
      ),
    );
    const { user, dialog } = await openAdd();
    await fillForm(user, dialog);

    await user.click(within(dialog).getByRole("button", { name: "Thêm nhân viên" }));

    expect(await within(dialog).findByText(/đã được dùng trong phòng khám/)).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("tells_the_owner_to_wait_on_a_429", async () => {
    api.post.mockImplementation(() => refused(429, "rate_limited", "Tạo tài khoản quá nhiều lần."));
    const { user, dialog } = await openAdd();
    await fillForm(user, dialog);

    await user.click(within(dialog).getByRole("button", { name: "Thêm nhân viên" }));

    expect(await within(dialog).findByText(/đợi một phút/)).toBeTruthy();
  });
});

describe("editing a member", () => {
  it("sends_only_the_changed_name_with_the_version", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Sửa Mai Anh" }));
    const dialog = await screen.findByRole("dialog");
    const name = within(dialog).getByLabelText("Họ tên");
    await user.clear(name);
    await user.type(name, "Mai Anh Thư");
    await user.click(within(dialog).getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() => expect(api.patch).toHaveBeenCalledTimes(1));
    expect(api.patch.mock.calls[0]?.[1]).toMatchObject({
      params: { path: { user_id: "u-mai" } },
      body: { version: 1, display_name: "Mai Anh Thư" },
    });
    const body = (api.patch.mock.calls[0]?.[1] as { body: Record<string, unknown> }).body;
    expect(body).not.toHaveProperty("role");
    expect(body).not.toHaveProperty("active");
  });

  it("keeps_save_off_until_something_changed", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Sửa Mai Anh" }));
    const dialog = await screen.findByRole("dialog");

    expect(
      within(dialog).getByRole("button", { name: "Lưu thay đổi" }).hasAttribute("disabled"),
    ).toBe(true);
    expect(within(dialog).getByLabelText("Email đăng nhập").hasAttribute("disabled")).toBe(true);
  });

  it("locks_the_role_on_the_own_account", async () => {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();

    await user.click(cards().getByRole("button", { name: "Sửa Nguyễn Thanh Hà" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/không thể tự đổi vai trò/)).toBeTruthy();
  });
});

describe("resetting a password", () => {
  async function openReset() {
    const user = userEvent.setup();
    renderPage(OWNER_PERMISSIONS);
    await ready();
    await user.click(cards().getByRole("button", { name: "Đặt lại mật khẩu của Mai Anh" }));
    const dialog = await screen.findByRole("dialog");
    return { user, dialog };
  }

  it("warns_that_the_person_is_signed_out_everywhere", async () => {
    const { dialog } = await openReset();

    expect(within(dialog).getByText(/sẽ bị đăng xuất khỏi mọi thiết bị ngay/)).toBeTruthy();
  });

  it("needs_the_same_password_twice", async () => {
    const { user, dialog } = await openReset();
    await user.type(within(dialog).getByLabelText("Mật khẩu mới"), "mat-khau-moi-1");
    await user.type(within(dialog).getByLabelText("Nhập lại mật khẩu mới"), "mat-khau-moi-2");

    await user.click(within(dialog).getByRole("button", { name: "Đặt lại mật khẩu" }));

    expect(await within(dialog).findByText("Hai ô mật khẩu chưa giống nhau.")).toBeTruthy();
    expect(api.post).not.toHaveBeenCalled();
  });

  it("posts_the_new_password_for_that_member", async () => {
    const { user, dialog } = await openReset();
    await user.type(within(dialog).getByLabelText("Mật khẩu mới"), "mat-khau-moi-1");
    await user.type(within(dialog).getByLabelText("Nhập lại mật khẩu mới"), "mat-khau-moi-1");

    await user.click(within(dialog).getByRole("button", { name: "Đặt lại mật khẩu" }));

    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0]?.[0]).toBe("/api/v1/admin/users/{user_id}/password");
    expect(api.post.mock.calls[0]?.[1]).toMatchObject({
      params: { path: { user_id: "u-mai" } },
      body: { new_password: "mat-khau-moi-1" },
    });
    expect(await screen.findByText("Đã đặt lại mật khẩu cho Mai Anh.")).toBeTruthy();
  });

  it("tells_the_owner_to_slow_down_on_a_429", async () => {
    api.post.mockImplementation(() =>
      refused(429, "rate_limited", "Đặt lại mật khẩu quá nhiều lần."),
    );
    const { user, dialog } = await openReset();
    await user.type(within(dialog).getByLabelText("Mật khẩu mới"), "mat-khau-moi-1");
    await user.type(within(dialog).getByLabelText("Nhập lại mật khẩu mới"), "mat-khau-moi-1");

    await user.click(within(dialog).getByRole("button", { name: "Đặt lại mật khẩu" }));

    expect(await within(dialog).findByText(/thao tác quá nhanh/)).toBeTruthy();
  });
});
