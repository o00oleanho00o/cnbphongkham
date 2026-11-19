/** The signed-in account: its email and a password change (which ends every other login). */
import { type FormEvent, useState } from "react";

import { api } from "../lib/api";
import { getSession, setSession } from "../lib/session";
import { Button, Card, Field, Input, Notice, PageHeader } from "../ui/kit";

interface SessionOut {
  token: string;
  expires_at: string;
  email: string;
}

export function AccountPage() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [notice, setNotice] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  async function change(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      const session = await api.post<SessionOut>("/v1/plugins/web/password", {
        current_password: current,
        new_password: next,
      });
      setSession({ token: session.token, email: session.email, expiresAt: session.expires_at });
      setCurrent("");
      setNext("");
      setNotice({ tone: "success", text: "Đã đổi mật khẩu. Các nơi khác đang đăng nhập đã bị đăng xuất." });
    } catch (err) {
      setNotice({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader title="Tài khoản" subtitle={getSession()?.email} />
      <Card title="Đổi mật khẩu">
        <form onSubmit={change} className="max-w-md space-y-4">
          <Field label="Mật khẩu hiện tại">
            <Input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} />
          </Field>
          <Field label="Mật khẩu mới" hint="Ít nhất 10 ký tự">
            <Input
              type="password"
              autoComplete="new-password"
              required
              minLength={10}
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </Field>
          {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}
          <Button type="submit" busy={busy}>
            Đổi mật khẩu
          </Button>
        </form>
      </Card>
    </div>
  );
}
