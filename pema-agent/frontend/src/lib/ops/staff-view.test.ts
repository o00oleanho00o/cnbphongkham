import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import {
  ROLE_HINT,
  STAFF_ROLES,
  activeQuery,
  asStaffRole,
  buildUpdate,
  lastLoginLabel,
  lockConfirmation,
  rowActions,
  staffErrorMessage,
  staleAfter,
  validateCreate,
  validatePasswordPair,
  type StaffForm,
  type StaffUser,
} from "./staff-view";

const USER: StaffUser = {
  id: "u-1",
  display_name: "Mai Anh",
  email: "maianh@phongkham.test",
  role: "cs_staff",
  active: true,
  last_login_at: null,
  created_at: "2026-09-01T09:00:00+07:00",
  version: 3,
};

const FORM: StaffForm = {
  displayName: "Nhân viên mới",
  email: "moi@phongkham.test",
  role: "reception",
  password: "mat-khau-8-ky-tu",
  passwordAgain: "mat-khau-8-ky-tu",
};

describe("the roles of the picker", () => {
  it("offers_the_accountant_with_a_hint_and_never_the_patient", () => {
    expect(STAFF_ROLES).toContain("accountant");
    expect(STAFF_ROLES).not.toContain("patient");
    expect(asStaffRole("accountant")).toBe("accountant");
    expect(ROLE_HINT.accountant).toContain("không duyệt đơn thuốc");
    expect(Object.keys(ROLE_HINT).sort()).toEqual([...STAFF_ROLES].sort());
  });
});

describe("rowActions", () => {
  describe("given a viewer who cannot change staff (the manager)", () => {
    it("no_button_is_shown", () => {
      // Given
      const viewer = { id: "me", canManage: false };

      // When
      const actions = rowActions(USER, viewer);

      // Then
      expect(actions).toEqual({
        edit: false,
        editRole: false,
        resetPassword: false,
        toggleLock: false,
      });
    });
  });

  describe("given the owner looking at another account", () => {
    it("every_button_is_shown", () => {
      // Given
      const viewer = { id: "me", canManage: true };

      // When
      const actions = rowActions(USER, viewer);

      // Then
      expect(actions).toEqual({
        edit: true,
        editRole: true,
        resetPassword: true,
        toggleLock: true,
      });
    });
  });

  describe("given the owner looking at their own account", () => {
    it("only_the_name_can_be_edited_and_lock_and_reset_are_hidden", () => {
      // Given
      const viewer = { id: USER.id, canManage: true };

      // When
      const actions = rowActions(USER, viewer);

      // Then
      expect(actions).toEqual({
        edit: true,
        editRole: false,
        resetPassword: false,
        toggleLock: false,
      });
    });
  });
});

describe("activeQuery", () => {
  it.each([
    ["all", undefined],
    ["active", true],
    ["locked", false],
  ] as const)("status_chip_%s_maps_to_the_backend_filter", (status, expected) => {
    expect(activeQuery(status)).toBe(expected);
  });
});

describe("validateCreate", () => {
  it("a_complete_form_is_accepted", () => {
    expect(validateCreate(FORM)).toBeNull();
  });

  it("a_blank_name_is_refused", () => {
    expect(validateCreate({ ...FORM, displayName: "   " })).toBe("Hãy nhập họ tên.");
  });

  it("an_email_without_a_domain_is_refused", () => {
    expect(validateCreate({ ...FORM, email: "khong-phai-email" })).toContain("Email đăng nhập");
  });

  it("a_short_password_is_refused_with_the_floor", () => {
    expect(validateCreate({ ...FORM, password: "ngan", passwordAgain: "ngan" })).toContain(
      "8 ký tự",
    );
  });

  it("two_different_passwords_are_refused", () => {
    expect(validateCreate({ ...FORM, passwordAgain: "mat-khau-khac-nhau" })).toBe(
      "Hai ô mật khẩu chưa giống nhau.",
    );
  });
});

describe("validatePasswordPair", () => {
  it("a_matching_pair_of_eight_characters_is_accepted", () => {
    expect(validatePasswordPair("12345678", "12345678")).toBeNull();
  });

  it("seven_characters_are_refused", () => {
    expect(validatePasswordPair("1234567", "1234567")).toContain("8 ký tự");
  });
});

describe("buildUpdate", () => {
  it("only_the_changed_fields_and_the_version_are_sent", () => {
    // Given
    const form = { displayName: "Mai Anh Mới", role: asStaffRole(USER.role) };

    // When
    const update = buildUpdate(USER, form, true);

    // Then
    expect(update).toEqual({ version: 3, display_name: "Mai Anh Mới" });
  });

  it("a_role_change_is_sent_when_the_viewer_may_change_it", () => {
    expect(buildUpdate(USER, { displayName: USER.display_name, role: "manager" }, true)).toEqual({
      version: 3,
      role: "manager",
    });
  });

  it("a_role_change_is_dropped_on_the_viewers_own_account", () => {
    expect(
      buildUpdate(USER, { displayName: USER.display_name, role: "manager" }, false),
    ).toBeNull();
  });

  it("nothing_changed_means_nothing_to_save", () => {
    expect(
      buildUpdate(USER, { displayName: "  Mai Anh ", role: asStaffRole(USER.role) }, true),
    ).toBeNull();
  });
});

describe("staffErrorMessage", () => {
  it("a_stale_version_asks_to_try_again_after_the_reload", () => {
    const message = staffErrorMessage(new ApiError(409, "x", "version_conflict"));

    expect(message).toContain("đã được tải lại");
  });

  it("a_taken_email_shows_the_sentence_of_the_backend", () => {
    const backend = "Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác.";

    expect(staffErrorMessage(new ApiError(409, backend, "invalid_state"))).toBe(backend);
  });

  it("a_refusal_of_the_last_owner_shows_the_sentence_of_the_backend", () => {
    const backend = "Phòng khám phải luôn có ít nhất một chủ phòng khám đang hoạt động.";

    expect(staffErrorMessage(new ApiError(422, backend, "validation_failed"))).toBe(backend);
  });

  it("too_many_attempts_say_to_wait_a_minute", () => {
    expect(staffErrorMessage(new ApiError(429, "Rate limited", "rate_limited"))).toContain(
      "một phút",
    );
  });

  it("a_missing_account_says_the_list_was_reloaded", () => {
    expect(staffErrorMessage(new ApiError(404, "not found", "not_found"))).toContain("tải lại");
  });

  it("a_forbidden_answer_says_there_is_no_permission", () => {
    expect(staffErrorMessage(new ApiError(403, "forbidden", "forbidden"))).toContain(
      "không có quyền",
    );
  });

  it("an_unknown_failure_gets_a_generic_sentence", () => {
    expect(staffErrorMessage(new Error("boom"))).toBe("Có lỗi xảy ra. Hãy thử lại.");
  });
});

describe("staleAfter", () => {
  it("a_stale_version_and_a_missing_account_make_the_list_stale", () => {
    expect(staleAfter(new ApiError(409, "x", "version_conflict"))).toBe(true);
    expect(staleAfter(new ApiError(404, "x", "not_found"))).toBe(true);
  });

  it("a_validation_error_does_not", () => {
    expect(staleAfter(new ApiError(422, "x", "validation_failed"))).toBe(false);
  });
});

describe("lockConfirmation", () => {
  it("locking_says_that_every_session_ends_at_once", () => {
    const text = lockConfirmation(USER);

    expect(text.tone).toBe("danger");
    expect(text.confirmLabel).toBe("Khóa tài khoản");
    expect(text.message).toContain("đăng xuất khỏi mọi thiết bị");
    expect(text.title).toContain("Mai Anh");
  });

  it("unlocking_says_that_a_new_sign_in_is_needed", () => {
    const text = lockConfirmation({ ...USER, active: false });

    expect(text.tone).toBe("normal");
    expect(text.confirmLabel).toBe("Mở khóa");
    expect(text.message).toContain("đăng nhập mới");
  });
});

describe("lastLoginLabel", () => {
  it("a_person_who_never_signed_in_is_labelled_so", () => {
    expect(lastLoginLabel(USER, () => "x")).toBe("Chưa đăng nhập lần nào");
  });

  it("the_last_sign_in_uses_the_given_formatter", () => {
    const label = lastLoginLabel(
      { last_login_at: "2026-09-20T09:00:00+07:00" },
      () => "20/09 09:00",
    );

    expect(label).toBe("Đăng nhập cuối 20/09 09:00");
  });
});
