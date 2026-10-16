// @vitest-environment jsdom
// Cài đặt của agent: each field says where its value comes from and goes back to the profile, a save sends only what
// changed, a text kept in the system warns that the file is not in use and offers "Dùng lại file", a refusal of the
// agent shows next to the form, and "Xóa mọi cài đặt đã lưu" clears everything after a confirmation.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./settings-page";

const SHOWN = {
  timezone: "Asia/Ho_Chi_Minh",
  failure_reply: "Xin lỗi, hệ thống đang bận.",
  variables: { clinic_name: "Phòng khám Pema", tone: "lịch sự" },
  persona: "Bạn là trợ lý của {{clinic_name}}.",
  rules: "Không chẩn đoán bệnh.",
  memory_enabled: true,
  memory_agent_chars: 2200,
  memory_user_chars: 1400,
  sources: {
    timezone: "profile",
    failure_reply: "profile",
    variables: "profile",
    persona: "profile",
    rules: "profile",
    memory_enabled: "profile",
    memory_agent_chars: "profile",
    memory_user_chars: "profile",
  },
  stored: false,
  version: 0,
  updated_by: null,
};

const withSources = (sources: Record<string, string>, extra = {}) => ({
  ...SHOWN,
  ...extra,
  stored: true,
  sources: { ...SHOWN.sources, ...sources },
});

type Reply = { status?: number; body: unknown };
type Call = { method: string; url: string; body: unknown };

/** A fake agent over the browser's fetch (an outside system); every call is written down. */
function fakeAgent(shown: object = SHOWN, answers: Record<string, Reply> = {}): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", (url: string, init?: RequestInit) => {
    const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
    const method = init?.method ?? "GET";
    calls.push({ method, url, body });
    const reply = answers[`${method} ${url}`] ?? { body: shown };
    return Promise.resolve(
      new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 }),
    );
  });
  return calls;
}

const mutations = (calls: Call[]) => calls.filter((c) => c.method !== "GET");
const SETTINGS_URL = "/agent/v1/admin/settings";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the settings of the agent", () => {
  it("shows_every_field_and_says_the_change_applies_from_the_next_reply", async () => {
    fakeAgent();
    render(<SettingsPage />);

    expect(await screen.findByDisplayValue("Asia/Ho_Chi_Minh")).toBeTruthy();
    expect(screen.getByDisplayValue("Xin lỗi, hệ thống đang bận.")).toBeTruthy();
    expect(screen.getByDisplayValue("Bạn là trợ lý của {{clinic_name}}.")).toBeTruthy();
    expect(screen.getByDisplayValue("Không chẩn đoán bệnh.")).toBeTruthy();
    expect(screen.getByDisplayValue("Phòng khám Pema")).toBeTruthy();
    expect(screen.getByDisplayValue("2200")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Bật trí nhớ" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    expect(screen.getByText(/áp dụng từ lượt trả lời tiếp theo của agent/)).toBeTruthy();
  });

  it("marks_a_stored_field_as_edited_and_the_others_as_following_the_profile", async () => {
    fakeAgent(withSources({ failure_reply: "db" }));
    render(<SettingsPage />);

    await screen.findByDisplayValue("Xin lỗi, hệ thống đang bận.");

    expect(screen.getAllByText("Đã chỉnh")).toHaveLength(1);
    expect(screen.getAllByText("Theo profile").length).toBeGreaterThan(3);
    expect(screen.getAllByRole("button", { name: /^Về mặc định/ })).toHaveLength(1);
  });

  it("shows_the_last_editor_when_there_is_one", async () => {
    fakeAgent(withSources({ rules: "db" }, { updated_by: "owner@pema.test" }));
    render(<SettingsPage />);

    expect(await screen.findByText("Sửa lần cuối bởi owner@pema.test")).toBeTruthy();
  });
});

describe("a save", () => {
  it("sends_only_the_fields_that_changed", async () => {
    const calls = fakeAgent(SHOWN, {
      [`PATCH ${SETTINGS_URL}`]: {
        body: withSources({ timezone: "db" }, { timezone: "Asia/Bangkok" }),
      },
    });
    render(<SettingsPage />);

    fireEvent.change(await screen.findByDisplayValue("Asia/Ho_Chi_Minh"), {
      target: { value: "Asia/Bangkok" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    expect(await screen.findByText(/Đã lưu - áp dụng từ lượt trả lời tiếp theo/)).toBeTruthy();
    expect(mutations(calls)).toEqual([
      { method: "PATCH", url: SETTINGS_URL, body: { timezone: "Asia/Bangkok" } },
    ]);
    expect(screen.getAllByText("Đã chỉnh")).toHaveLength(1);
  });

  it("has_nothing_to_save_until_something_changes", async () => {
    fakeAgent();
    render(<SettingsPage />);

    const save = await screen.findByRole("button", { name: "Lưu thay đổi" });

    expect((save as HTMLButtonElement).disabled).toBe(true);
  });

  it("adds_a_variable_and_sends_it_by_name", async () => {
    const calls = fakeAgent();
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "+ Thêm biến" }));
    fireEvent.change(screen.getByLabelText("Tên biến 3"), { target: { value: "hotline" } });
    fireEvent.change(screen.getByLabelText("Giá trị của hotline"), {
      target: { value: "0900 000 000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    await waitFor(() =>
      expect(mutations(calls)).toEqual([
        {
          method: "PATCH",
          url: SETTINGS_URL,
          body: { variables: { hotline: "0900 000 000" } },
        },
      ]),
    );
  });

  it("refuses_a_memory_size_out_of_range_before_sending_anything", async () => {
    const calls = fakeAgent();
    render(<SettingsPage />);

    fireEvent.change(await screen.findByDisplayValue("2200"), { target: { value: "50" } });

    expect(screen.getByText("Trong khoảng 100 - 20000")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Lưu thay đổi" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(mutations(calls)).toEqual([]);
  });

  it("shows_the_message_of_a_refusal_and_keeps_what_was_typed", async () => {
    fakeAgent(SHOWN, {
      [`PATCH ${SETTINGS_URL}`]: {
        status: 422,
        body: { error: { kind: "invalid", message: "unknown time zone 'Mars/Olympus'" } },
      },
    });
    render(<SettingsPage />);

    fireEvent.change(await screen.findByDisplayValue("Asia/Ho_Chi_Minh"), {
      target: { value: "Mars/Olympus" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Lưu thay đổi" }));

    expect(await screen.findByText("unknown time zone 'Mars/Olympus'")).toBeTruthy();
    expect(screen.getByDisplayValue("Mars/Olympus")).toBeTruthy();
  });
});

describe("going back to the profile", () => {
  it("sends_null_for_a_stored_field_from_its_own_button", async () => {
    const calls = fakeAgent(withSources({ failure_reply: "db" }), {
      [`PATCH ${SETTINGS_URL}`]: { body: SHOWN },
    });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /^Về mặc định: Lời trả lời/ }));

    expect(await screen.findByText(/đã về mặc định của profile/)).toBeTruthy();
    expect(mutations(calls)).toEqual([
      { method: "PATCH", url: SETTINGS_URL, body: { failure_reply: null } },
    ]);
  });

  it("sends_null_for_one_variable_so_the_profiles_value_comes_back", async () => {
    const calls = fakeAgent(withSources({ variables: "db" }), {
      [`PATCH ${SETTINGS_URL}`]: { body: SHOWN },
    });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Về giá trị profile: tone" }));

    await waitFor(() =>
      expect(mutations(calls)).toEqual([
        { method: "PATCH", url: SETTINGS_URL, body: { variables: { tone: null } } },
      ]),
    );
  });
});

describe("a persona or rules kept in the system", () => {
  const WARNING =
    /Đang dùng bản đã lưu trong hệ thống, không dùng file SOUL\.md \(hoặc AGENTS\.md\)/;

  it("warns_for_the_stored_persona_only", async () => {
    fakeAgent(withSources({ persona: "db" }));
    render(<SettingsPage />);

    await screen.findByDisplayValue("Không chẩn đoán bệnh.");

    expect(screen.getAllByText(WARNING)).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /^Dùng lại file/ })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Dùng lại file: Vai trò" })).toBeTruthy();
  });

  it("warns_for_both_when_both_are_stored", async () => {
    fakeAgent(withSources({ persona: "db", rules: "db" }));
    render(<SettingsPage />);

    await screen.findByDisplayValue("Không chẩn đoán bệnh.");

    expect(screen.getAllByText(WARNING)).toHaveLength(2);
  });

  it("shows_no_warning_when_both_follow_the_files", async () => {
    fakeAgent();
    render(<SettingsPage />);

    await screen.findByDisplayValue("Không chẩn đoán bệnh.");

    expect(screen.queryByText(WARNING)).toBeNull();
    expect(screen.queryByRole("button", { name: /Dùng lại file/ })).toBeNull();
  });

  it("goes_back_to_the_file_only_after_a_confirmation", async () => {
    const calls = fakeAgent(withSources({ persona: "db" }), {
      [`PATCH ${SETTINGS_URL}`]: { body: SHOWN },
    });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Dùng lại file: Vai trò" }));
    const dialog = (await screen.findByText("Dùng lại file?")).closest<HTMLElement>(
      '[role="dialog"]',
    );
    expect(mutations(calls)).toEqual([]);
    fireEvent.click(within(dialog as HTMLElement).getByRole("button", { name: "Dùng lại file" }));

    await waitFor(() =>
      expect(mutations(calls)).toEqual([
        { method: "PATCH", url: SETTINGS_URL, body: { persona: null } },
      ]),
    );
    await waitFor(() => expect(screen.queryByText(WARNING)).toBeNull());
  });

  it("keeps_the_stored_text_when_the_confirmation_is_cancelled", async () => {
    const calls = fakeAgent(withSources({ rules: "db" }));
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Dùng lại file: Quy tắc" }));
    fireEvent.click(await screen.findByRole("button", { name: "Hủy" }));

    await waitFor(() => expect(screen.queryByText("Dùng lại file?")).toBeNull());
    expect(mutations(calls)).toEqual([]);
  });
});

describe("clearing everything stored", () => {
  it("deletes_after_a_confirmation_and_shows_the_profiles_values", async () => {
    const calls = fakeAgent(withSources({ failure_reply: "db" }, { failure_reply: "Bận" }), {
      [`DELETE ${SETTINGS_URL}`]: { body: SHOWN },
    });
    render(<SettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Xóa mọi cài đặt đã lưu" }));
    const dialog = (await screen.findByText("Xóa mọi cài đặt đã lưu?")).closest<HTMLElement>(
      '[role="dialog"]',
    );
    fireEvent.click(within(dialog as HTMLElement).getByRole("button", { name: "Xóa cài đặt" }));

    expect(await screen.findByDisplayValue("Xin lỗi, hệ thống đang bận.")).toBeTruthy();
    expect(mutations(calls)).toEqual([{ method: "DELETE", url: SETTINGS_URL, body: undefined }]);
  });

  it("is_not_offered_while_nothing_is_stored", async () => {
    fakeAgent();
    render(<SettingsPage />);

    const button = await screen.findByRole("button", { name: "Xóa mọi cài đặt đã lưu" });

    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("loading", () => {
  it("shows_the_error_when_the_settings_cannot_be_read", async () => {
    fakeAgent(SHOWN, {
      [`GET ${SETTINGS_URL}`]: {
        status: 403,
        body: { error: { kind: "forbidden", message: "Không đủ quyền" } },
      },
    });
    render(<SettingsPage />);

    expect(await screen.findByText("Không đủ quyền")).toBeTruthy();
  });
});
