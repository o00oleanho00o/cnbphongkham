"use client";

// Add or edit a staff member (`POST /api/v1/admin/users`, `PATCH /api/v1/admin/users/{user_id}`). Only the
// owner reaches it (`admin.users`). The e-mail is the sign-in name and cannot be changed after creation; the
// role of your OWN account is shown but locked, because the backend refuses to re-role yourself.
import { useState, type FormEvent } from "react";

import { SecretInput } from "@/components/admin/shared/secret-input";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  MAX_NAME_LENGTH,
  ROLE_HINT,
  STAFF_ROLES,
  asStaffRole,
  buildUpdate,
  staffErrorMessage,
  staleAfter,
  validateCreate,
  type StaffRole,
  type StaffUser,
} from "@/lib/ops/staff-view";
import { ROLE_LABEL } from "@/lib/session/session-context";

const ROLE_OPTIONS: SelectOption[] = STAFF_ROLES.map((role) => ({
  value: role,
  label: ROLE_LABEL[role],
}));

export function StaffSheet({
  staff,
  isSelf,
  onClose,
  onSaved,
  onStale,
}: {
  /** null = add a new member */
  staff: StaffUser | null;
  /** the person editing is looking at their own account */
  isSelf: boolean;
  onClose: () => void;
  onSaved: () => void;
  /** the list on screen is out of date (stale version, account gone): reload it */
  onStale: () => void;
}) {
  const toast = useToast();
  const [displayName, setDisplayName] = useState(staff?.display_name ?? "");
  const [email, setEmail] = useState(staff?.email ?? "");
  const [role, setRole] = useState<StaffRole>(staff ? asStaffRole(staff.role) : "cs_staff");
  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const canEditRole = !isSelf;
  const update = staff ? buildUpdate(staff, { displayName, role }, canEditRole) : null;
  const roleChanges = staff !== null && canEditRole && role !== staff.role;
  const canSave = staff ? update !== null : displayName.trim() !== "" && email.trim() !== "";

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (staff === null) {
      const problem = validateCreate({ displayName, email, role, password, passwordAgain });
      if (problem) {
        setError(problem);
        return;
      }
    }
    setBusy(true);
    try {
      if (staff) {
        if (update === null) return;
        await unwrap(
          http.PATCH("/api/v1/admin/users/{user_id}", {
            params: { path: { user_id: staff.id } },
            body: update,
          }),
        );
        toast.push("success", "Đã lưu thay đổi.");
      } else {
        await unwrap(
          http.POST("/api/v1/admin/users", {
            body: { display_name: displayName.trim(), email: email.trim(), role, password },
          }),
        );
        toast.push("success", "Đã thêm nhân viên.");
      }
      onSaved();
    } catch (err) {
      setError(staffErrorMessage(err));
      if (staleAfter(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={staff ? "Sửa nhân viên" : "Thêm nhân viên"}
      subtitle={
        staff
          ? "Đổi họ tên hoặc vai trò. Email đăng nhập không đổi được."
          : "Tạo tài khoản và mật khẩu ban đầu; nhân viên đổi lại ở Tài khoản của tôi."
      }
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="staff-form" disabled={busy || !canSave}>
            {busy ? "Đang lưu..." : staff ? "Lưu thay đổi" : "Thêm nhân viên"}
          </PrimaryButton>
        </>
      }
    >
      <form id="staff-form" onSubmit={(e) => void save(e)} className="space-y-4" noValidate>
        <Field label="Họ tên" htmlFor="staff-name">
          <input
            id="staff-name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            maxLength={MAX_NAME_LENGTH}
            autoComplete="off"
            className="gc-input w-full"
          />
        </Field>
        <Field
          label="Email đăng nhập"
          htmlFor="staff-email"
          hint={staff ? undefined : "Dùng để đăng nhập, không trùng với nhân viên khác."}
        >
          <input
            id="staff-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={staff !== null}
            maxLength={254}
            autoComplete="off"
            className="gc-input w-full disabled:opacity-60"
          />
        </Field>
        <Field
          label="Vai trò"
          htmlFor="staff-role"
          hint={isSelf ? "Bạn không thể tự đổi vai trò của chính mình." : ROLE_HINT[role]}
        >
          <SelectMenu
            id="staff-role"
            size="md"
            value={role}
            options={ROLE_OPTIONS}
            disabled={!canEditRole}
            onChange={(value) => setRole(asStaffRole(value))}
          />
        </Field>
        {roleChanges && (
          <Notice tone="warn">
            Đổi vai trò sẽ đăng xuất người này khỏi mọi thiết bị; họ đăng nhập lại để dùng quyền
            mới.
          </Notice>
        )}
        {staff === null && (
          <>
            <Field
              label="Mật khẩu ban đầu"
              htmlFor="staff-password"
              hint="Ít nhất 8 ký tự. Hãy báo mật khẩu cho nhân viên qua kênh riêng."
            >
              <SecretInput id="staff-password" value={password} onChange={setPassword} />
            </Field>
            <Field label="Nhập lại mật khẩu" htmlFor="staff-password-again">
              <SecretInput
                id="staff-password-again"
                value={passwordAgain}
                onChange={setPasswordAgain}
              />
            </Field>
          </>
        )}
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
