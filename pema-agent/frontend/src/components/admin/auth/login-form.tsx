// ported from: web/src/pages/login-page.tsx
"use client";

// Deviations: the original asked for one shared dashboard password; the clinic CRM has users, so the
// form is clinic + email + password and the BE answers with an httpOnly session cookie (`POST
// /api/v1/auth/login`). After sign-in we read the permissions to land on the first screen the role may
// open. `next` is only honoured for same-origin paths.
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { SecretInput } from "@/components/admin/shared/secret-input";
import { anhNen } from "@/lib/admin/shared/background-image";
import { useTheme } from "@/lib/admin/shared/use-theme";
import { ApiError, http, unwrap } from "@/lib/api/client";
import { homeFor } from "@/lib/nav";
import type { Permission } from "@/lib/session/session-context";

const DEFAULT_CLINIC = process.env.NEXT_PUBLIC_DEFAULT_CLINIC_SLUG ?? "";
const CLINIC_KEY = "pema-agent-clinic";

function readClinic(): string {
  try {
    return localStorage.getItem(CLINIC_KEY) ?? DEFAULT_CLINIC;
  } catch {
    return DEFAULT_CLINIC;
  }
}

/** Only same-origin absolute paths: `//evil.example` and `https://...` are ignored. */
function safeNext(raw: string | null): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return null;
  return raw;
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [clinic, setClinic] = useState(readClinic);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { theme } = useTheme();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.POST("/api/v1/auth/login", {
          body: { clinic_slug: clinic.trim(), email: email.trim(), password },
        }),
      );
      try {
        localStorage.setItem(CLINIC_KEY, clinic.trim());
      } catch {
        /* localStorage bị chặn: chỉ mất phần nhớ phòng khám */
      }
      const me = await unwrap(http.GET("/api/v1/me"));
      const granted = new Set<Permission>(me.permissions);
      const home = homeFor((needs) => needs.some((p) => granted.has(p)));
      router.replace(safeNext(params.get("next")) ?? home);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Không kết nối được server");
    } finally {
      setBusy(false);
    }
  }

  // Ảnh sóng chỉ ở vùng nhận diện (đăng nhập), không đặt sau bảng dữ liệu.
  return (
    <div
      className="flex min-h-[100dvh] items-center justify-center bg-canvas bg-cover bg-center px-4"
      style={{ backgroundImage: `url(${anhNen(theme)})` }}
    >
      <form onSubmit={submit} className="gc-card w-full max-w-sm p-6 sm:p-8">
        <div className="mb-6 flex flex-col items-center gap-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- fixed brand asset */}
          <img src="/pema-logo.png" alt="Pema" width={294} height={156} className="h-20 w-auto" />
          <h1 className="text-[17px] font-semibold text-ink">Đăng nhập CSKH</h1>
          <div className="text-[13px] text-ink-soft">Chăm sóc khách hàng và trợ lý AI</div>
        </div>

        <label htmlFor="clinic" className="mb-1.5 block text-[13px] font-medium text-ink">
          Phòng khám
        </label>
        <input
          id="clinic"
          value={clinic}
          onChange={(e) => setClinic(e.target.value)}
          autoComplete="organization"
          placeholder="ma-phong-kham"
          className="gc-input mb-3 w-full"
        />

        <label htmlFor="email" className="mb-1.5 block text-[13px] font-medium text-ink">
          Email
        </label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          autoFocus
          className="gc-input mb-3 w-full"
        />

        <label htmlFor="password" className="mb-1.5 block text-[13px] font-medium text-ink">
          Mật khẩu
        </label>
        <SecretInput id="password" value={password} onChange={setPassword} className="mb-3" />
        {error && (
          <p role="alert" className="mb-3 text-[13px] text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy || !clinic.trim() || !email.trim() || password.length === 0}
          className="min-h-11 w-full rounded-lg bg-brand-500 py-2.5 text-[14px] font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {busy ? "Đang đăng nhập..." : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}
