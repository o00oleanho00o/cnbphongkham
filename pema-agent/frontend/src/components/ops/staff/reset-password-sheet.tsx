"use client";

// The owner sets a new password for another staff member (`POST /api/v1/admin/users/{user_id}/password`).
// The new password is typed twice; every session of that person ends at once, which the form says before
// it is sent. At most 5 resets a minute per owner (429).
import { useState, type FormEvent } from "react";

import { SecretInput } from "@/components/admin/shared/secret-input";
import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  MIN_PASSWORD_LENGTH,
  staffErrorMessage,
  staleAfter,
  validatePasswordPair,
  type StaffUser,
} from "@/lib/ops/staff-view";

export function ResetPasswordSheet({
  staff,
  onClose,
  onDone,
  onStale,
}: {
  staff: StaffUser;
  onClose: () => void;
  onDone: () => void;
  onStale: () => void;
}) {
  const toast = useToast();
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = validatePasswordPair(password, again);
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.POST("/api/v1/admin/users/{user_id}/password", {
          params: { path: { user_id: staff.id } },
          body: { new_password: password },
        }),
      );
      toast.push("success", `Đã đặt lại mật khẩu cho ${staff.display_name}.`);
      onDone();
    } catch (err) {
      setError(staffErrorMessage(err));
      if (staleAfter(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Đặt lại mật khẩu"
      subtitle={`${staff.display_name} · ${staff.email}`}
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="reset-password-form" disabled={busy || !password}>
            {busy ? "Đang lưu..." : "Đặt lại mật khẩu"}
          </PrimaryButton>
        </>
      }
    >
      <form
        id="reset-password-form"
        onSubmit={(e) => void submit(e)}
        className="space-y-4"
        noValidate
      >
        <Notice tone="warn">
          {staff.display_name} sẽ bị đăng xuất khỏi mọi thiết bị ngay và phải đăng nhập bằng mật
          khẩu mới. Hãy báo mật khẩu cho họ qua kênh riêng.
        </Notice>
        <Field
          label="Mật khẩu mới"
          htmlFor="reset-password"
          hint={`Ít nhất ${MIN_PASSWORD_LENGTH} ký tự.`}
        >
          <SecretInput id="reset-password" value={password} onChange={setPassword} />
        </Field>
        <Field label="Nhập lại mật khẩu mới" htmlFor="reset-password-again">
          <SecretInput id="reset-password-again" value={again} onChange={setAgain} />
        </Field>
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}
