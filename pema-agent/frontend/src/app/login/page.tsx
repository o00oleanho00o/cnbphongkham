// ported from: web/src/pages/login-page.tsx (route; the form is components/admin/auth/login-form.tsx)
import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/components/admin/auth/login-form";

export const metadata: Metadata = { title: "Đăng nhập" };

export default function LoginPage() {
  // useSearchParams (the `next` target) needs a Suspense boundary for static prerender.
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
