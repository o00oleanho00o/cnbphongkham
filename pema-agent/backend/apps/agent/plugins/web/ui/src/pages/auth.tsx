/** Before any page: the first account (while the agent has none) or the sign-in. */
import { type FormEvent, useEffect, useState } from "react";

import { api, errorText } from "../lib/api";
import { setSession } from "../lib/session";
import { Button, Field, Input, Notice } from "../ui/kit";

interface SessionOut {
  token: string;
  expires_at: string;
  email: string;
}

export function AuthScreen() {
  const [needsSetup, setNeedsSetup] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .get<{ needs_setup: boolean }>("/v1/hooks/web/state")
      .then((state) => setNeedsSetup(state.needs_setup))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : errorText(err, 0)));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const path = needsSetup ? "/v1/hooks/web/setup" : "/v1/hooks/web/login";
      const session = await api.post<SessionOut>(path, { email, password });
      setSession({ token: session.token, email: session.email, expiresAt: session.expires_at });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không đăng nhập được");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-card border border-line bg-surface p-6 shadow-card">
        <h1 className="text-subtitle font-bold text-heading">Pema Agent</h1>
        <p className="mt-1 mb-5 text-small text-ink-soft">
          {needsSetup
            ? "Lần đầu mở: tạo tài khoản quản trị. Chỉ tạo được một lần, người tạo trước là chủ."
            : "Đăng nhập bảng điều khiển của agent."}
        </p>
        <div className="space-y-4">
          <Field label="Email">
            <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Mật khẩu" hint={needsSetup ? "Ít nhất 10 ký tự" : undefined}>
            <Input
              type="password"
              autoComplete={needsSetup ? "new-password" : "current-password"}
              required
              minLength={needsSetup ? 10 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          {error && <Notice tone="danger">{error}</Notice>}
          <Button type="submit" busy={busy} disabled={needsSetup === null} className="w-full">
            {needsSetup ? "Tạo tài khoản" : "Đăng nhập"}
          </Button>
        </div>
      </form>
    </main>
  );
}
