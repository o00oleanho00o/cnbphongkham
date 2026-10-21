// ported from: web/src/pages/login-page.tsx (route; the form is components/admin/auth/login-form.tsx)
import { createFileRoute } from "@tanstack/react-router";
import { Suspense } from "react";

import { LoginForm } from "@/components/admin/auth/login-form";

function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

export const Route = createFileRoute("/login/")({
  head: () => ({ meta: [{ title: "Đăng nhập · Pema CSKH" }] }),
  component: LoginPage,
});
