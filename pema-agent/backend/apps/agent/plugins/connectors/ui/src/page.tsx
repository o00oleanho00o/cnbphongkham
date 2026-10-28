/** "Connectors": the services that plug into the agent (Zalo ...), the key of each, and the channels they registered. */
import { useCallback, useEffect, useState } from "react";

import { connectors, messageOf } from "./client";
import { ui } from "./sdk";
import type { Connector, Created } from "./types";

const NAME = /^[a-z0-9][a-z0-9_-]{0,31}$/;

function when(iso: string | null): string {
  if (!iso) return "chưa lần nào";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString("vi-VN");
}

function KeyNotice({ created, onDone }: { created: Created; onDone: () => void }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(created.key);
      setCopied(true);
    } catch {
      setCopied(false); // the key stays on screen to select by hand
    }
  }

  return (
    <ui.Notice tone="warning">
      <div className="space-y-2">
        <p className="font-medium">Khóa của connector {created.name} (chỉ hiện một lần, đóng đi là không xem lại được)</p>
        <code className="block break-all rounded-field border border-line bg-field px-3 py-2 text-small text-ink select-all">
          {created.key}
        </code>
        <p className="text-label">Dán vào biến môi trường CONNECTOR_KEY của connector rồi khởi động lại nó.</p>
        <div className="flex flex-wrap gap-2">
          <ui.Button variant="secondary" onClick={() => void copy()}>
            {copied ? "Đã chép" : "Chép khóa"}
          </ui.Button>
          <ui.Button variant="ghost" onClick={onDone}>
            Đã lưu khóa, đóng
          </ui.Button>
        </div>
      </div>
    </ui.Notice>
  );
}

function AddCard({ onCreated }: { onCreated: (created: Created) => void }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const invalid = name !== "" && !NAME.test(name);

  async function add() {
    setBusy(true);
    setError("");
    try {
      onCreated(await connectors.create(name));
      setName("");
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ui.Card title="Thêm connector">
      <div className="space-y-3">
        <ui.Field
          label="Tên"
          hint="a-z, 0-9, gạch ngang hoặc gạch dưới, tối đa 32 ký tự (ví dụ zalo). Kênh của connector phải tên giống nó hoặc bắt đầu bằng tên đó và dấu gạch ngang."
          error={invalid ? "Tên chỉ gồm a-z, 0-9, - và _, tối đa 32 ký tự." : undefined}
        >
          <ui.Input value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
        </ui.Field>
        <ui.Button busy={busy} disabled={name === "" || invalid} onClick={() => void add()}>
          Thêm và cấp khóa
        </ui.Button>
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      </div>
    </ui.Card>
  );
}

function ConnectorCard({ connector, onChanged }: { connector: Connector; onChanged: () => void }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function revoke() {
    setBusy(true);
    setError("");
    try {
      await connectors.revoke(connector.name);
      setAsking(false);
      onChanged();
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ui.Card
      title={connector.name}
      aside={
        <ui.Badge tone={connector.revoked ? "danger" : "success"}>{connector.revoked ? "Đã thu hồi" : "Đang dùng"}</ui.Badge>
      }
    >
      <div className="space-y-3">
        <p className="text-small text-ink-soft">
          Cấp lúc {when(connector.created_at)}
          {connector.revoked && `, thu hồi lúc ${when(connector.revoked_at)}`}
        </p>
        {connector.channels.length === 0 ? (
          <ui.Empty>{connector.revoked ? "Các kênh đã gỡ khi thu hồi." : "Chưa đăng ký kênh nào."}</ui.Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-small">
              <thead>
                <tr className="text-label text-ink-soft">
                  <th className="py-1 pr-4 font-medium">Kênh</th>
                  <th className="py-1 pr-4 font-medium">Trạng thái</th>
                  <th className="py-1 font-medium">Thấy lần cuối</th>
                </tr>
              </thead>
              <tbody>
                {connector.channels.map((channel) => (
                  <tr key={channel.name} className="border-t border-line text-ink">
                    <td className="py-1.5 pr-4">{channel.name}</td>
                    <td className="py-1.5 pr-4">
                      <ui.Badge tone={channel.listening ? "success" : "warning"}>
                        {channel.listening ? "Đang nhận tin" : "Đang khởi động"}
                      </ui.Badge>
                    </td>
                    <td className="py-1.5">{when(channel.seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!connector.revoked &&
          (asking ? (
            <ui.Notice tone="danger">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>Thu hồi {connector.name}? Connector im ngay và các kênh của nó bị gỡ.</span>
                <span className="flex gap-2">
                  <ui.Button variant="danger" busy={busy} onClick={() => void revoke()}>
                    Thu hồi
                  </ui.Button>
                  <ui.Button variant="secondary" disabled={busy} onClick={() => setAsking(false)}>
                    Giữ lại
                  </ui.Button>
                </span>
              </div>
            </ui.Notice>
          ) : (
            <ui.Button variant="danger" onClick={() => setAsking(true)}>
              Thu hồi khóa
            </ui.Button>
          ))}
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      </div>
    </ui.Card>
  );
}

export function ConnectorsPage() {
  const [found, setFound] = useState<Connector[] | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setFound(await connectors.list());
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function added(next: Created) {
    setCreated(next);
    void load();
  }

  return (
    <div className="space-y-4">
      <ui.PageHeader
        title="Connectors"
        subtitle="Dịch vụ ngoài (Zalo, Facebook, Telegram...) nối vào agent bằng khóa. Mỗi connector tự đăng ký kênh chat của nó; thu hồi khóa là connector đó im ngay."
      />
      {created && <KeyNotice created={created} onDone={() => setCreated(null)} />}
      {error && (
        <ui.Notice tone="danger">
          <span className="flex flex-wrap items-center justify-between gap-2">
            {error}
            <ui.Button variant="secondary" onClick={() => void load()}>
              Thử lại
            </ui.Button>
          </span>
        </ui.Notice>
      )}
      <AddCard onCreated={added} />
      {found === null && !error && <ui.Empty>Đang tải…</ui.Empty>}
      {found?.length === 0 && <ui.Empty>Chưa có connector nào.</ui.Empty>}
      {found?.map((connector) => (
        <ConnectorCard key={connector.name} connector={connector} onChanged={() => void load()} />
      ))}
    </div>
  );
}
