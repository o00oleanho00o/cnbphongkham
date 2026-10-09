/** API keys for programs that call the chat API (`/v1/chat`); a new key is shown once, then only its name. */
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { api } from "../lib/api";
import { Button, Card, Empty, Field, Input, Notice, PageHeader } from "../ui/kit";

interface ApiKey {
  id: string;
  name: string;
  created_at: string;
}

export function ApiKeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [name, setName] = useState("");
  const [made, setMade] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setKeys(await api.get<ApiKey[]>("/v1/plugins/web/api-keys"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api.post<ApiKey & { key: string }>("/v1/plugins/web/api-keys", { name });
      setMade(created.key);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key: ApiKey) {
    if (!window.confirm(`Thu hồi khóa "${key.name}"? Chương trình đang dùng nó sẽ bị từ chối ngay.`)) return;
    try {
      await api.del(`/v1/plugins/web/api-keys/${key.id}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi");
    }
  }

  return (
    <div>
      <PageHeader title="API key" subtitle="Cho chương trình khác gọi API chat của agent (không vào được trang quản trị)" />
      <div className="space-y-4">
        <Card title="Tạo khóa mới">
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <div className="min-w-60 flex-1">
              <Field label="Tên (để nhớ ai dùng)">
                <Input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
            </div>
            <Button type="submit" busy={busy}>
              Tạo khóa
            </Button>
          </form>
          {made && (
            <div className="mt-4 space-y-2">
              <Notice tone="warning">Chép khóa này ngay: nó chỉ hiện một lần.</Notice>
              <code className="block rounded-tile border border-line bg-tile p-3 text-small break-all">{made}</code>
              <Button variant="secondary" onClick={() => void navigator.clipboard.writeText(made)}>
                Chép
              </Button>
            </div>
          )}
        </Card>
        {error && <Notice tone="danger">{error}</Notice>}
        <Card title="Khóa đang dùng">
          {keys.length === 0 ? (
            <Empty>Chưa có khóa nào.</Empty>
          ) : (
            <ul className="divide-y divide-line">
              {keys.map((key) => (
                <li key={key.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span>
                    <span className="block font-medium">{key.name}</span>
                    <span className="block text-label text-ink-soft">
                      pak_{key.id}_… · tạo {new Date(key.created_at).toLocaleString("vi-VN")}
                    </span>
                  </span>
                  <Button variant="danger" onClick={() => void revoke(key)}>
                    Thu hồi
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
