# Giao thức connector, phiên bản 1

Thứ duy nhất agent và một connector (Zalo, Facebook, Telegram…) chung. Connector là dịch vụ riêng, viết bằng ngôn
ngữ bất kỳ, không import code của agent. Kế hoạch và lý do: `PLAN-zalo-service.md`. JSON, UTF-8; mọi id là chuỗi.

## 1. Khóa và chữ ký

- Agent cấp cho mỗi connector một **khóa**: 32 byte ngẫu nhiên, mã hóa `base64url` không đệm, hiện **một lần** trên
  trang quản trị (Điều khiển agent > Connectors). Agent giữ khóa niêm phong trong DB; connector giữ trong biến môi
  trường `CONNECTOR_KEY`. Thu hồi trên trang quản trị là connector đó bị từ chối ngay.
- Mọi yêu cầu, hai chiều, mang ba header:
  - `X-Connector`: tên connector (`a-z0-9_-`, tối đa 32 ký tự, ví dụ `zalo`).
  - `X-Timestamp`: giây unix lúc ký.
  - `X-Signature`: hex của `HMAC-SHA256(key, timestamp + "\n" + METHOD + "\n" + path + "\n" + body)`. `key` là chuỗi
    base64url dùng làm byte UTF-8; `METHOD` viết hoa; `path` là đường dẫn như bên nhận thấy, không có query; `body` là
    thân thô (rỗng với GET/DELETE).
- Bên nhận từ chối **401** khi thiếu header, sai chữ ký (so sánh hằng thời gian), hoặc `|now - timestamp| > 300`
  giây. Thu hồi hay tên lạ cũng trả 401, không nói lý do.

## 2. Tên kênh

`a-z0-9_-`, tối đa 64 ký tự. Một connector chỉ được đăng ký kênh tên **đúng bằng tên connector, hoặc bắt đầu bằng
`<connector>-`** (connector `zalo` được `zalo`, `zalo-botthang`; không được `facebook-x`). Tên kênh là chính tên dùng
trong session của agent (`agent:kênh:cuộc chat:epoch`) và trong cài đặt (`follow_up.channels`).

## 3. Connector → agent

Gốc: `{AGENT_URL}/v1/hooks/connectors`. Ký như mục 1.

| Gọi | Thân | Trả |
|---|---|---|
| `PUT /channels/{name}` | `{"protocol": 1, "callback_url": "http://zalo:8089", "max_text_chars": null, "markdown": false, "rules": "", "disabled_tools": []}` | 200 `{}`. Đăng ký hoặc cập nhật kênh. Gọi lúc khởi động và mỗi khi cài đặt tài khoản đổi. `rules` là đoạn văn thêm vào prompt mỗi lượt của kênh này; `disabled_tools` là tên tool bị tắt cho kênh này; `max_text_chars` không dùng để tách (xem mục 4 `/send`) mà để agent biết giới hạn khi viết |
| `DELETE /channels/{name}` | | 200 `{}` |
| `POST /channels/{name}/inbound` | `{"conversation_id", "user_id", "message_id", "text", "metadata": {}}` | 200 `{"ingress_id": n}`. Agent lưu trước rồi mới trả lời. Cùng `message_id` hai lần trả cùng `ingress_id`, không chạy lại. 404 nếu kênh chưa đăng ký |
| `POST /channels/{name}/observed` | `{"conversation_id", "sender_id", "message_id", "text", "origin": "inbound\|own\|agent", "is_group": false, "sender_name": "", "user_id": "", "answered": false, "at": "<ISO 8601>", "metadata": {}}` | 200 `{}`. Tin agent chỉ quan sát (tin nhóm không trả lời, chủ tài khoản gõ từ máy khác, phản ứng) |
| `POST /channels/{name}/typing` | `{"conversation_id"}` | 200 `{}`. Khách đang gõ; agent chờ lâu hơn để gộp tin |

`metadata` là chuỗi sang chuỗi. Khóa agent hiểu: `thread_type` (`group` nếu cuộc chat nhóm), `observe` (`1` nếu
agent được báo lại câu trả lời của chính nó cho các plugin ghi hội thoại), `proactive` (do agent đặt, connector chép
lại nguyên khi gặp). Khóa lạ chuyển nguyên cho agent.

## 4. Agent → connector

Gốc: `callback_url` của kênh. Ký như mục 1 (`X-Connector` là tên connector của kênh).

| Gọi | Thân | Trả |
|---|---|---|
| `POST /send` | `{"delivery_id": "...", "channel", "conversation_id", "user_id", "reply_to", "text", "metadata": {}}` | 200 `{"sent": n}` (`n` phần). `text` là **cả câu trả lời**, chưa tách: connector làm sạch (bỏ markdown nếu không hiển thị được) và kiểm an toàn **ngay**, rồi trả 200 khi đã **nhận và lưu** câu trả lời, không chờ gửi xong. Việc tách theo giới hạn của nền tảng, gửi từng phần, nghỉ giữa các phần và thử lại khi nền tảng lỗi là của connector, chạy sau. Cùng `delivery_id` hai lần thì nhận một lần |
| `POST /typing` | `{"channel", "conversation_id", "metadata": {}}` | 200 `{}`. Lỗi bị bỏ qua |
| `GET /health` | | 200 `{}` |

Lỗi của `/send`, thân `{"error": "...", "retryable": true, "retry_after_s": null}`:

- **422**, `retryable: false`: không được gửi (lộ prompt, người dùng chặn, cuộc chat đã xóa). Agent ghi "không gửi", không thử lại.
- **429/503**, `retryable: true`, `retry_after_s` tùy chọn: agent thử lại (tối đa 4 lần, lùi dần).
- Quá 60 giây không trả lời: agent coi là lỗi, thử lại.

## 5. Giao diện quản trị của connector (tùy chọn)

Connector có trang quản trị thì tự phục vụ; web phòng khám chỉ chuyển tiếp. Không phần nào đi qua agent.

- Web phòng khám chuyển tiếp `/connectors/<tên>/<đường dẫn>` tới `<địa chỉ nội bộ của connector>/<đường dẫn>`, kèm
  token SSO ngắn hạn của nhân viên đang đăng nhập (cùng loại token web phòng khám đang gửi cho agent: `aud =
  pema-agent`). Connector tự kiểm token (JWKS của CRM) và quyền (owner, manager).
- `GET /v1/admin/ui` → `{"name": "zalo", "script": "/ui/client.js", "styles": []}`; đường dẫn tương đối gốc của
  connector. Tệp tĩnh dưới `/ui/`. Trang quản trị nạp vào cùng khung "Điều khiển agent" như trang của plugin.
- API quản trị của connector giữ nguyên đường dẫn hiện có (`/v1/plugins/zalo/...`) để trang cũ dùng lại được.

## 6. Bảo đảm

- **Không mất tin đến:** connector lưu tin vào hàng đợi của nó trước, đẩy sau, thử lại khi agent không trả lời
  (lùi dần), chỉ xóa sau khi nhận 200. Nền tảng như Zalo Bot không có offset nên đây là chỗ duy nhất giữ tin.
- **Không mất câu trả lời:** sau 200 của `/send`, câu trả lời nằm trong hàng gửi bền của connector; gửi lỗi thì
  connector tự thử lại, bỏ hẳn thì ghi log. Agent không biết các phần sau gửi được hay không.
- **Không gửi hai lần:** `delivery_id` (agent) và `message_id` (connector).
- **Tên kênh, `message_id`, `conversation_id`** do connector đặt và ổn định qua các lần khởi động.
