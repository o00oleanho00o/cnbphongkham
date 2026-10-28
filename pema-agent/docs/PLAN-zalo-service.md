# Kế hoạch: Zalo thành connector, tách tuyệt đối khỏi agent

Ghi 2026-10-23. Chủ chọn: tách Zalo khỏi agent **tuyệt đối, kiểu connector** (như connector Gmail của Claude
Code): hai bên chỉ chung một **giao thức HTTP có văn bản**, không chung một dòng code, không chung thư viện, không
chung lock, không chung khóa ngoài khóa agent cấp cho connector. Điều kiện: **không mất gì**. Chờ chủ nói "go"
(H11). Khi chủ nói go, kế hoạch này là văn bản duyệt L7: profile `clinic` bỏ plugin `zalo`, thêm plugin `connectors`.

## 0. Ý chính

- Agent có **một cửa chung cho connector** (plugin `connectors`, bundled, không biết Zalo là gì). Connector đăng ký
  kênh, đẩy sự kiện vào (tin đến, tin quan sát, khách đang gõ), nhận lệnh ra (gửi tin, hiện đang gõ). Agent cấp
  cho mỗi connector một khóa trên trang quản trị, như "thêm connector" rồi dán khóa.
- Zalo là connector `pema-agent/connectors/zalo/`: thư mục tự đứng, `pyproject` và `uv.lock` riêng, Dockerfile
  riêng, **không import gì từ `backend/`**. Giữ nguyên ~4.900 dòng code Zalo hiện có, thêm lớp nối mỏng.
- Giao thức là thứ duy nhất hai bên chung, viết ở `docs/CONNECTOR-PROTOCOL.md` (phiên bản 1). Ai cũng viết được
  connector khác (Facebook, Telegram, web chat) bằng ngôn ngữ bất kỳ mà không đọc code agent. Đây là bước đầu của
  "loop engineering bằng sự kiện và hook" mà chủ muốn.

## 1. Cái gì agent đang cho plugin Zalo, và sau này đi đường nào

Đọc `plugins/zalo/plugin.py`, `channel_hub.py`, `channels.py`, `host.py` (2026-10-23):

| Hiện nay (trong tiến trình) | Sau (qua giao thức) | Mất gì |
|---|---|---|
| `register_channel(adapter)`: `start`, `send`, `typing`, `on_typing`, `listens_to`, `prepare` | Một `ConnectorChannel` cho mỗi kênh đã đăng ký; `send`/`typing` là lệnh POST sang connector; `on_typing`, `listens_to` lấy từ sự kiện connector đẩy vào; `prepare` làm ở connector (mục 3) | Không |
| Tin đến → `hub._receiver` → `dispatcher.accept` (lưu trước, chạy sau, `heard` → ca) | Sự kiện `inbound` gọi đúng hàm đó | Không; connector lưu tin vào outbox của nó trước khi đẩy, vì `getUpdates` của Zalo Bot không có offset |
| `ctx.observe` (tin nhóm không trả lời, chủ tài khoản gõ, phản ứng) → plugin `conversations` | Sự kiện `observed` | Không |
| Hub báo "trả lời của agent" cho `conversations` qua `listens_to` | `listens_to` đọc cờ `observe` trong metadata của tin đến (connector đặt) | Không |
| `register_prompt_section` (quy tắc theo kênh, mỗi lượt) | Trường `rules` của kênh khi đăng ký; `connectors` có một `TurnSection` chung đọc theo kênh của lượt | Không |
| `register_hook(PreToolHook)` tắt tool theo tài khoản | Trường `disabled_tools` của kênh | Không |
| Tin chủ động (`Proactive.send_to` của ca nhắc lịch, chăm sóc lại) | Hub tìm kênh theo tên như cũ → `ConnectorChannel.send` | Không; `follow_up.channels = ["zalo-botthang"]` giữ nguyên tên |
| `queue_wait_by_prefix = { "zalo-" = … }` (gộp tin, chờ khách gõ) | Dữ liệu theo tên kênh, không đổi | Không |
| Retry gửi (`DeliverySettings`, 4 lần, backoff) | Như cũ; connector trả `retryable`, `retry_after_s` trong lỗi | Không |
| 3 job (đồng bộ tài khoản, giữ cầu nối chạy, tự nhận kết bạn) | Job của connector | Không |
| Route admin `/v1/plugins/zalo/*`, hook `/v1/hooks/zalo/*` (webhook bot, webhook cầu nối) | Route của connector | Không |
| 8 trang giao diện trong "Điều khiển agent" | Connector tự phục vụ; web phòng khám proxy `/connectors/zalo/*` tới nó như đang proxy `/agent/*` | Không |
| `ctx.storage` + `ctx.encrypt` (tài khoản, token niêm phong) | KV riêng của connector, niêm phong bằng khóa riêng `ZALO_SECRET_KEY` | Token bot nhập lại một lần trên giao diện mới (một tài khoản) |
| Ra internet qua proxy `egress`, container chỉ đọc | Connector `zalo` cùng cấu hình compose | Không |

Thêm được: `prepare` chặn lộ prompt giờ chặn **cả** câu trả lời trước khi tách phần (hôm nay hub tách trước rồi
mới `prepare` từng phần). Và tắt, gỡ, thay một connector không đụng tiến trình agent.

## 2. Giao thức connector, phiên bản 1 (`docs/CONNECTOR-PROTOCOL.md`)

Thứ duy nhất hai bên chung. JSON, UTF-8, mọi id là chuỗi.

**Khóa.** Agent cấp cho mỗi connector một khóa (32 byte ngẫu nhiên, hiện một lần trên trang quản trị). Agent giữ
khóa niêm phong (`ctx.encrypt`), connector giữ trong biến môi trường. Mọi yêu cầu hai chiều ký **HMAC-SHA256** trên
`timestamp + "\n" + method + "\n" + path + "\n" + body` bằng khóa đó, gửi `X-Connector: <tên>`,
`X-Timestamp: <unix giây>`, `X-Signature: <hex>`. Lệch quá 300 giây hoặc sai chữ ký: 401. Thu hồi khóa trên trang
quản trị là connector đó câm ngay.

**Connector → agent** (`/v1/hooks/connectors/...`, chỉ HMAC, không cookie):

| Gọi | Thân | Trả |
|---|---|---|
| `PUT /channels/{name}` | `{protocol: 1, callback_url, max_text_chars, markdown, rules, disabled_tools: [..]}` | 200. Gọi lúc khởi động và khi tài khoản đổi; cùng tên thì cập nhật |
| `DELETE /channels/{name}` | | 200 |
| `POST /channels/{name}/inbound` | `{conversation_id, user_id, message_id, text, metadata: {..}}` (metadata: `thread_type`, `observe`, tên người…) | `{ingress_id}`; trùng `message_id` trả bản cũ |
| `POST /channels/{name}/observed` | `{conversation_id, sender_id, message_id, text, origin, is_group, sender_name, user_id, at, metadata}` | 200 |
| `POST /channels/{name}/typing` | `{conversation_id}` | 200 |

**Agent → connector** (`callback_url` của kênh, chỉ HMAC):

| Gọi | Thân | Trả |
|---|---|---|
| `POST /send` | `{delivery_id, channel, conversation_id, user_id, reply_to, text, metadata}` (cả câu trả lời, chưa tách) | 200 `{sent: n}`; lỗi `{error, retryable, retry_after_s}` với 422 (không gửi, ví dụ lộ prompt) hay 503 (thử lại). Cùng `delivery_id` hai lần: gửi một |
| `POST /typing` | `{channel, conversation_id, metadata}` | 200; lỗi bỏ qua |
| `GET /health` | | 200 |

Tên kênh: `a-z0-9_-`, do connector đặt (`zalo-botthang`); session của agent vẫn là `agent:kênh:chat:epoch`.

## 3. Agent: plugin `connectors` (bundled, ~450 dòng)

- Bảng `agent_rt.connector` (`name`, `key_sealed`, `created_at`, `revoked_at`) và `agent_rt.connector_channel`
  (`name`, `connector`, `callback_url`, `max_text_chars`, `markdown`, `rules`, `disabled_tools`, `seen_at`).
- Route admin: `GET/POST /v1/plugins/connectors`, `DELETE .../{name}` (thu hồi). Trang quản trị nhỏ trong
  "Điều khiển agent": danh sách connector, nút Thêm (hiện khóa một lần), Thu hồi, kênh nào đang đăng ký và lần
  cuối thấy.
- Route hook theo mục 2, kiểm HMAC bằng khóa của connector ghi trong `X-Connector`.
- `ConnectorChannel(ChannelAdapter, ShowsTyping, ReportsTyping, FiltersListening)`: `send` gửi cả câu trả lời
  (khả năng báo `max_text_chars = None` cho hub), ánh xạ lỗi sang `ChannelSendError`; `typing` POST, bỏ qua lỗi;
  `on_typing` nhận `notify` của hub và gọi khi có sự kiện `typing`; `listens_to` đọc `metadata["observe"]`.
- Một `TurnSection("channel_rules")` và một `PreToolHook("channel_tools")` chung, đọc theo kênh của lượt.
- Tắt plugin `connectors` = mọi connector im lặng. Trang Tổng quan liệt kê kênh của connector như kênh khác
  (hub `status()` đã có).

Luật: H1 giữ (plugin không biết nền tảng nào; harness không đổi). H2: quy tắc và tool theo kênh là dữ liệu. L6:
connector không phải tool. L2 không đụng: connector không nói chuyện với CRM.

## 4. Connector `connectors/zalo/` (Python, FastAPI; ~800–1.000 dòng mới, ~4.900 dòng chuyển nguyên)

- Thư mục ngoài `backend/`: `pyproject.toml`, `uv.lock`, `Dockerfile` riêng; phụ thuộc chỉ `fastapi`, `uvicorn`,
  `httpx`, `pydantic`, `pyjwt[crypto]`, `cryptography`. **Không** `agent-core`, `agent_app`, `plugin_kit`,
  `secret-cipher`: những gì cần thì chép (ba kiểu dữ liệu của giao thức là model pydantic của connector; `split_reply`
  ~30 dòng; niêm phong token bằng `cryptography.fernet` ~15 dòng; kiểm token SSO bằng `pyjwt` + JWKS ~40 dòng).
- Chuyển nguyên từ `plugins/zalo`: `bot/`, `personal/`, `bridge/`, `format/`, `accounts.py`, `contacts.py`,
  `reaction_icons.py`, `models.py`, phần lớn `routes.py` và `plugin.py` (đổi `ctx.*` thành dịch vụ của chính nó),
  `ui/`. Mỗi chỗ chuyển giữ nguyên xử lý lỗi và kiểm tra đầu vào.
- Mới:
  - `agent_client.py`: đăng ký kênh, đẩy `inbound`/`observed`/`typing`, ký HMAC. **Outbox** trong KV: tin đến
    ghi trước, đẩy sau, thử lại theo backoff khi agent không trả lời; không mất tin vì agent đang khởi động lại.
  - `callback.py`: `POST /send`, `POST /typing`, `GET /health`; `send` kiểm HMAC → `prepare` (chặn lộ prompt, bỏ
    markdown) → `split_reply` → gửi từng phần theo tài khoản; chống trùng theo `delivery_id` (KV).
  - `store.py`: KV trong SQLite ở `/data/zalo.db` (stdlib `sqlite3`; một tiến trình, vài ghi mỗi giây). Giữ API
    `get/put/list/delete` như `PluginStorage` để `accounts.py` không đổi. Phương án lớn hơn, không chọn: Postgres
    riêng + role + alembic.
  - `auth.py`: route admin và giao diện nhận token SSO của web phòng khám (JWKS của CRM, `aud = pema-agent`,
    owner/manager = admin; từ chối `aud = pema-agent-events`), viết bằng `pyjwt`, cùng quy tắc plugin `sso`.
  - `main.py`: `uvicorn`, cổng 8089.
- Biến môi trường: `AGENT_URL=http://agent:8088`, `CALLBACK_URL=http://zalo:8089`, `CONNECTOR_NAME=zalo`,
  `CONNECTOR_KEY` (từ trang quản trị agent), `ZALO_SECRET_KEY` (niêm phong token), `CRM_JWKS_URL`, `PUBLIC_URL`
  (webhook bot; trống thì long polling).

## 5. Web phòng khám

- `frontend/src/routes/connectors/$.ts`: proxy `/connectors/<tên>/**` tới địa chỉ nội bộ của connector đó
  (`PEMA_CONNECTOR_URLS=zalo=http://zalo:8089`) với token SSO, sao chép `routes/agent/$.ts` và
  `lib/server/agent-proxy.ts`. Menu "Điều khiển agent" thêm mục Zalo trỏ sang trang do connector phục vụ. ~80 dòng.

## 6. Hạ tầng

- `connectors/zalo/Dockerfile`: stage `bun` + `bridge` + `ui` (chuyển từ `agent.Dockerfile`) + Python slim; build
  context là `connectors/zalo/`, nên đổi gì trong `backend/` không build lại connector và ngược lại.
  `agent.Dockerfile` bỏ ba stage đó: image agent không còn Bun.
- `docker-compose.yml`: service `zalo` (mạng như agent: `egress` cho ra internet; `read_only`, `cap_drop`, volume
  `/data`), không publish cổng; `docker-compose.local.yml` bật nó; `.env.example`, `gen-secrets.sh` thêm
  `ZALO_SECRET_KEY`; `CONNECTOR_KEY` do chủ dán sau khi cấp trên giao diện; `backup-postgres.sh` thêm
  `/data/zalo.db` vào gói sao lưu (như ảnh phòng khám).
- `agents/clinic/agent.toml`: `enabled` bỏ `"zalo"`, thêm `"connectors"`; `agents/dev` không đổi.

## 7. Thứ tự làm (mỗi bước một commit, agent cũ vẫn chạy cho tới bước 7)

1. Viết `docs/CONNECTOR-PROTOCOL.md` (mục 2) trước code.
2. Plugin `connectors` trong agent (mục 3), kèm trang quản trị. Kiểm tay: cấp khóa, đăng ký một kênh giả bằng
   `curl`, đẩy một tin, nhận `send` về một server giả.
3. Connector `connectors/zalo` chạy một mình (mục 4), chưa nối agent: trang tài khoản, nhập token bot, long polling.
4. Nối: outbox đẩy tin vào agent, `/send` nhận trả lời; thử một vòng chat thật trên Zalo.
5. Giao diện: proxy và menu (mục 5).
6. Hạ tầng (mục 6), build hai image, chạy stack demo.
7. Gỡ `plugins/zalo` khỏi agent; đổi `agent.toml`; sửa `agent-crm-boundary.md` (L6: client Zalo nay ở connector
   `zalo`), chạy `/archify` vì cấu trúc dịch vụ đổi; cập nhật `HANDOFF-agent-v2.md`, `infra/README.md`.
8. Cut-over: cấp khóa, dán vào `.env`, nhập lại token bot; kiểm: chat đến và trả lời, "Gửi thử ngay" của một ca,
   tin nhóm vào plugin `conversations`, khách gõ thì agent chờ, thu hồi khóa thì connector câm.

Test: theo `test-writing.md`, không unit test; e2e Playwright thêm một spec mở trang Zalo qua proxy và trang
Connectors. Vòng chat thật kiểm tay ở bước 4 và 8.

## 8. Cái giá và rủi ro

- Thêm một dịch vụ, một image, một khóa cấp tay, một cổng nội bộ. Hai lần nhảy HTTP mỗi tin (mili giây; Zalo chậm
  hơn nhiều).
- Agent chết thì tin nằm trong outbox của connector, không mất; connector chết thì hub thử lại 4 lần như hôm nay
  rồi ghi "không gửi".
- Khoảng 1.400–1.800 dòng mới (giao thức, plugin, lớp nối, outbox, trang Connectors). Code cũ chuyển nguyên không
  đếm là mới. Vài chục dòng bị chép (`split_reply`, niêm phong, kiểm JWT) là giá của tách tuyệt đối; chép có chủ ý,
  ghi nguồn ở đầu file.
- Chưa kiểm khi viết kế hoạch: plugin `sso` tôi chưa đọc hết, nên `auth.py` có thể cần thêm ~40 dòng để đúng từng
  quy tắc vai trò.
