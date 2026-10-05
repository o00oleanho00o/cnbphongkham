// ported from: web/src/pages/login-page.tsx (sign-in itself is /login; this route keeps the account side)
"use client";

// "Tài khoản của tôi": who is signed in and the change-password section of the original dashboard
// (which lived inside the Cấu hình page there; PORT-MAP puts both under `components/admin/auth`).
import { PageHeader } from "@/components/admin/layout/page-header";
import { ChangePasswordSection } from "@/components/admin/auth/change-password-section";
import { IconLock } from "@/components/admin/shared/dashboard-icons";
import { ROLE_LABEL, useSession } from "@/lib/session/session-context";

export default function AuthPage() {
  const { user } = useSession();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        icon={IconLock}
        title="Tài khoản của tôi"
        subtitle={`${user.display_name} · ${ROLE_LABEL[user.role]} · ${user.clinic_name}`}
      />
      <div className="gc-card p-5">
        <ChangePasswordSection />
      </div>
    </div>
  );
}
