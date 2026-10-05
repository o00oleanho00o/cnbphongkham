// ported from: web/src/pages/login-page.tsx (sign-in itself is /login; this route keeps the account side)
"use client";

// "Tài khoản của tôi": who is signed in and the change-password section of the original dashboard
// (which lived inside the Cấu hình page there; PORT-MAP puts both under `components/admin/auth`).
import { PageHeader } from "@/components/admin/layout/page-header";
import { ChangePasswordSection } from "@/components/admin/auth/change-password-section";
import { ROLE_LABEL, useSession } from "@/lib/session/session-context";

export default function AuthPage() {
  const { user } = useSession();
  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Tài khoản của tôi"
        subtitle={`${user.display_name} · ${ROLE_LABEL[user.role]} · ${user.clinic_name}`}
      />
      <div className="rounded-card border border-line bg-surface p-5 shadow-card">
        <ChangePasswordSection />
      </div>
    </div>
  );
}
