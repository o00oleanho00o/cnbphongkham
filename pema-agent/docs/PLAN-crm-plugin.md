# Kế hoạch: plugin `crm`, agent xem giờ trống, lưu liên hệ, đặt và giữ lịch hẹn; CRM báo lịch cho agent để nhắc hẹn

**Trạng thái (2026-10-20): bước 1 đã viết, chưa commit; các bước còn lại CHỜ CHỦ NÓI "GO", chưa code.** Chủ chọn:
- gọi API, không MCP;
- **tạm bỏ bước lễ tân xác nhận** và mọi việc báo nhân viên (HANDOFF mục 12);
- khách xem, xác nhận, dời, hủy lịch của mình trong lúc chat;
- **nhắc hẹn theo kiểu "loop engineering": CRM báo sự kiện cho agent, agent hẹn giờ tới mốc. Không có chuyện agent hỏi CRM
  theo chu kỳ** (đã bỏ cách hỏi 10 phút một lần). Nền tảng ý tưởng: `IDEAS-agent-loops.md`;
- **(2026-10-20) ẩn credential:** tiến trình agent **không giữ khóa nào của CRM**. Một dịch vụ trung gian `crm-signer` giữ
  khóa riêng và ký từng yêu cầu; CRM chỉ giữ khóa công khai. Chiều CRM → agent cũng ký bằng khóa bất đối xứng, nên agent
  chỉ giữ khóa công khai (mục 3.9);
- **(2026-10-20) cứng hóa và hạn chế internet:** test khóa danh sách tool, `agent_writes` tắt, biến môi trường của
  agent theo danh sách cho phép, container `read_only`/`cap_drop`/`no-new-privileges`, agent chỉ ở mạng nội bộ và ra
  internet qua một proxy đi ra (mục 3.10);
- **tạm gác:** duyệt tay có điều kiện (hủy sát giờ, lần dời thứ 3, người mới) và **danh sách tên miền được ra internet**:
  proxy đi ra chạy ở chế độ chỉ ghi log cho tới khi chủ chốt danh sách (HANDOFF mục 14).

Việc này **mở một đường mới giữa agent và CRM** (hai chiều, mỗi chiều một khóa), nên đổi luật L2, L3, L4 của
`.claude/rules/agent-crm-boundary.md` (L5: chủ quyết bằng văn bản, chính là kế hoạch này). L1 giữ nguyên: agent vẫn
không chạm database `pema`.

**Bước 1 (CRM, phần cổng agent) đã viết**, 22 test mới của cổng qua trên một Postgres tạm (`scratch_pema`, cổng 25432,
không phải DB demo). **Bộ test đầy đủ của `apps/api` chưa chạy** (bắt buộc vì có migration và đổi tên hai hàm dùng
chung). Khác với bản viết đầu:
- đồng ý nhận nhắc lưu trong bảng `clinic.consent` có sẵn (loại `messaging`, nguồn `agent:<kênh>`), không thêm cột;
  tham số là `messages_consent`;
- audit dùng mã có sẵn (`patient.create`, `consent.record`, `appointment.create`/`update`/`confirm`/`cancel`) cộng
  `patient_channel.create`; người làm là `agent`, `source = agent`;
- lịch trả cho agent không có `note` (nhân viên ghi nhận xét nội bộ ở đó);
- nhận cả số bàn 11 chữ số; giờ hẹn phải cách hiện tại ít nhất 30 phút;
- chủ phòng khám giữ mọi quyền trừ sáu quyền `agent.*`.

## 1. Mục tiêu

**A. Trong lúc chat**, thay nhân viên mở CRM làm tay: đưa giờ còn trống, lưu tên và số điện thoại, đặt lịch, cho
khách xem lại lịch của mình, xác nhận, dời hoặc hủy lịch theo lời khách. *(Bước 1-3.)*

**B. Nhắc hẹn:** tối hôm trước (khoảng 24 giờ) và 3 giờ trước giờ khám, nhắn khách đã đồng ý nhận nhắc; câu trả lời
của khách đi theo đường A. CRM báo mọi thay đổi lịch cho agent; agent hẹn giờ tới mốc. *(Bước 2, 4, 5.)*

**Ràng buộc an toàn:** agent bị jailbreak cũng chỉ làm được các việc trên **cho chính người đang chat**. Nó không đọc
được dữ liệu bệnh nhân khác, không đụng lịch của người khác, không đặt lịch đứng tên người khác.

**Không phải mục tiêu (bản này):** lễ tân xác nhận, báo nhân viên (kể cả khi khách hủy muộn); gộp hồ sơ trùng, nối
hồ sơ cũ với Zalo; nhắn khách vắng mặt; đường gửi nguyên văn không qua model (mục 3.6).

## 2. Hiện trạng (đọc 2026-10-19)

**CRM (lịch hẹn, người, quyền)**
- `clinic.appointment`: `patient_id`, `doctor_id?`, `room_id?`, `starts_at`, `duration_min`, `status` (`booked` →
  `confirmed` → …; hủy hoặc vắng thì giờ được trả lại), `note`, `version` (khóa lạc quan), `updated_at` (trigger).
  **Không có dịch vụ trên lịch hẹn.** Giờ làm viết cứng 08:00-18:00, nghỉ 12:00-13:00; ca làm của bác sĩ chỉ hiển thị.
- Chỉ có bảng `clinic.patient` (`phone` lưu nguyên văn, không duy nhất); không có bảng khách tiềm năng, không có Zalo ID.
- Xác thực chỉ có cookie phiên nhân viên; `AGENT_PERMISSIONS` từng rỗng.
- Dùng lại được: `validate_slot`, `find_conflict`, khóa advisory khi đặt, hàm chuyển trạng thái, `audit.record` (actor
  `agent`), `Idempotency-Key` + `find_replay`, `FixedWindowLimiter`, sự kiện `appointments.changed`.
- **Vòng nền của CRM:** `AppLifecycle` (`composition/app_runtime.py`) chạy `crm-rules` và `retention` trong tiến trình
  API, và `appointment_events.install_listener` đã đánh thức vòng `crm-rules` khi một lịch đổi (sau khi commit).
  Hiện listener này chỉ nhận một hàm; outbox cần thêm một người nghe nữa (xem 3.4).

**Agent**
- `ToolContext.channel`, `ToolContext.user_id`: hub gắn, model không điền.
- `ctx.register_job` (việc chạy nền của plugin), `ctx.register_routes(kind="hooks")` (route mở ở `/v1/hooks/<plugin>`,
  plugin tự kiểm người gọi), migration riêng của plugin vào schema `agent_rt`.
- Mẫu ký HMAC: `plugins/zalo/personal/signing.py` (`X-Pema-Timestamp`, `X-Pema-Signature`, dung sai 300 giây).
- `DispatcherOutbox`: đường gửi chủ động của vòng chăm sóc lại (đưa chỉ dẫn vào hàng đợi, model viết hoặc trả `SKIP`,
  tin đi với cờ `proactive`, chịu công tắc tắt khẩn và hạn mức ngày của bridge Zalo).
- Cổng 8088 của container agent không mở ra ngoài máy (chỉ trong mạng Docker).

## 3. Thiết kế

### 3.1 Nguyên tắc

1. **Model không bao giờ chọn "là ai".** Danh tính khách là `ToolContext.channel` + `user_id`; code plugin gửi chúng,
   tham số tool không có trường nào nói về người. Không có tool nhận số điện thoại để tra.
2. **CRM giữ mối nối khách ↔ hồ sơ.** Agent không cầm `patient_id`; mã lịch do model đưa chỉ có tác dụng khi lịch
   thuộc hồ sơ đã nối, không thì CRM trả 404.
3. **Hai chiều, hai khóa bất đối xứng, tiến trình agent không giữ khóa riêng nào của hai chiều.** Agent → CRM:
   `crm-signer` ký JWT ngắn hạn bằng khóa riêng của nó; CRM kiểm bằng khóa công khai; sáu quyền `agent.*`, chỉ nhóm
   `/agent-gateway`. CRM → agent: CRM ký sự kiện bằng khóa riêng của CRM; agent kiểm bằng khóa công khai (JWKS đã có),
   chỉ một route nhận. Lấy trộm được gì trong container agent cũng không ký được yêu cầu hay sự kiện.
4. **Không trả dữ liệu người khác.** Giờ trống chỉ là danh sách giờ. Sự kiện và danh sách đối soát chỉ có mã, kênh, ID
   ngoài, giờ, trạng thái; không tên, không số điện thoại.
5. **Sự kiện mô tả trạng thái, không mô tả thay đổi.** Mỗi sự kiện mang trạng thái đầy đủ của lịch và `version`; nhận
   trùng, nhận lộn thứ tự, nhận thiếu đều không làm agent sai (bỏ bản cũ hơn bản đang giữ).

### 3.2 Phía CRM: cổng agent (bước 1, đã viết)

**Bảng** `clinic.patient_channel` (migration `0002`): (`clinic_id`, `channel`, `external_id`) duy nhất → `patient_id`.
Là dữ liệu CRM, agent không đọc được, không view, hàm SQL hay role riêng.

**Quyền** (`rbac`): `agent.slots.read`, `agent.contact.write`, `agent.booking.write`, `agent.appointment.read`,
`agent.appointment.change`, `agent.reminders.read`. `AGENT_PERMISSIONS` đúng sáu quyền này; không vai trò nhân viên nào
có.

**Xác thực máy** (`api/agent_gateway_auth.py`, **bước 1b đã làm 2026-10-20**; thay khóa Bearer tĩnh băm
SHA-256 của bước 1): `Authorization: Bearer <JWT>` do `crm-signer` ký bằng Ed25519;
CRM giữ **khóa công khai** (`PEMA_AGENT_GATEWAY_PUBLIC_KEYS`: một hoặc hai khóa, để đổi khóa không gián đoạn). CRM kiểm:
chữ ký, `iss = pema-crm-signer`, `aud = pema-agent-gateway`, `exp` ≤ 2 phút sau `iat`, `scope` chứa quyền mà route cần,
`jti` chưa dùng (nhớ trong bộ nhớ tới khi hết hạn). Không đặt khóa công khai thì cả nhóm route trả 404. Giới hạn 300
lượt gọi mỗi phút cho cả nhóm, 10 lần ghi mỗi giờ cho mỗi người chat. Các route, quyền và test T6-T8 giữ nguyên.
Khóa công khai viết dạng base64url của 32 byte (trường `x` của JWK), cách nhau bằng dấu phẩy. Thiếu quyền trong
`scope` thì 403; mọi lỗi khác của token thì 401.

**Route** `/api/v1/agent-gateway` (ký hiệu `C` = `/contacts/{channel}/{external_id}`):

| Endpoint | Vào | Ra |
|---|---|---|
| `GET /free-slots` | `day_from`, `days` (1-14), `duration_min` | giờ bắt đầu theo ngày |
| `PUT C` | `full_name`, `phone`, `messages_consent` | `{created, messages_consent}` |
| `POST C/appointments` | `starts_at`, `duration_min`, `note` + `Idempotency-Key` | lịch đã tạo |
| `GET C/appointments` | không | lịch sắp tới (`id`, `starts_at`, `duration_min`, `status`) |
| `POST C/appointments/{id}/confirm` | không | lịch sau khi đổi |
| `POST C/appointments/{id}/reschedule` | `starts_at`, `duration_min?` + `Idempotency-Key` | lịch sau khi đổi |
| `POST C/appointments/{id}/cancel` | `reason` | lịch sau khi đổi |
| `GET /reminders` | `hours` (1-48) | **chỉ để đối soát (3.4):** lịch `booked`/`confirmed` của người đã nối và đã đồng ý nhận nhắc |

Quy tắc đã cài:
- **Giờ trống:** bước 15 phút trong giờ làm, không quá khứ, cách hiện tại ≥ 30 phút; một giờ còn trống khi số lịch
  đang hiệu lực chồng lên nó ít hơn số bác sĩ đang hoạt động (lịch agent đặt chưa có bác sĩ).
- **Liên hệ:** chuẩn hóa số Việt Nam, sai thì 422; lần đầu tạo hồ sơ (`source = agent:<kênh>`) và mối nối; lần sau
  **không sửa** hồ sơ, chỉ cập nhật đồng ý nhận nhắc; **không gộp theo số điện thoại**.
- **Đặt và dời:** cần mối nối (không có thì 409); kiểm giờ bằng bộ kiểm của quầy lễ tân cộng khóa sức chứa; bắt buộc
  `Idempotency-Key`; tối đa 2 lịch sắp tới mỗi người và 3 lần dời mỗi lịch.
- **Xác nhận và hủy:** chỉ lịch của đúng người, đang `booked`/`confirmed`, chưa tới giờ; dùng lại hàm chuyển trạng
  thái có sẵn. Lý do hủy ghi "Khách hủy qua chat: …".
- Mỗi lần ghi: `audit.record` (không đưa tên, số), `announce` để màn lịch tải lại.

### 3.3 Phía agent: plugin `apps/agent/plugins/crm/` (bước 3)

**Cài đặt** (`plugin.toml`): `base_url` (mặc định `http://crm-signer:8090/agent-gateway`: **gọi qua `crm-signer`, không
gọi thẳng API**), `timeout_s` (8), `reminders.enabled` (**mặc định tắt**), `reminders.quiet_hours` (21:00-07:00),
`reminders.marks_h` (24, 3). **Plugin không giữ khóa hay bí mật nào**: kiểm sự kiện bằng khóa công khai của CRM, đọc từ
JWKS mà plugin `sso` đã tải. `crm-signer` không trả lời thì tool báo "CRM đang không trả lời".

**`client.py`**: `httpx.AsyncClient` tới đúng `base_url`, không theo chuyển hướng; lỗi CRM thành câu đọc được ("giờ đó
vừa có người đặt", "số điện thoại không hợp lệ", "lịch vừa thay đổi, xem lại", "CRM đang không trả lời, hẹn khách
nhân viên gọi lại").

**Bảy tool** (kênh và ID khách lấy từ `ToolContext`; thiếu một trong hai, ví dụ phiên CLI, thì từ chối):

| Tool | Tham số model điền | `read_only` |
|---|---|---|
| `crm_free_slots` | `day_from`, `days`, `duration_min?` | có |
| `crm_save_contact` | `full_name`, `phone`, `messages_consent` | không |
| `crm_book_appointment` | `starts_at`, `duration_min?`, `note` | không |
| `crm_my_appointments` | không | có |
| `crm_confirm_appointment` | `appointment_id` | không |
| `crm_reschedule_appointment` | `appointment_id`, `starts_at`, `duration_min?` | không |
| `crm_cancel_appointment` | `appointment_id`, `reason` | không |

`Idempotency-Key` = băm(`session_id`, tên tool, `appointment_id`, `starts_at`). `crm_save_contact` còn ghi vào bảng
`crm_person` của plugin: (`channel`, `external_id`) → cuộc chat để gửi tin nhắc (xem 3.5, điều cần xác minh).

**Đã làm (bước 4, 2026-10-21), khác chữ ở trên:**
- Người là `ToolContext.channel` + `user_id`, và **kênh phải do một plugin chat sở hữu** (`ctx.channel_plugin`): lượt
  của CLI hay khung chat thử của nhân viên (`http`) bị từ chối, nên không tạo hồ sơ giả trong CRM.
- `Idempotency-Key` = băm(`session_id`, giờ bắt đầu lượt, tên tool, tham số): gọi lại trong cùng lượt dùng chung khóa;
  khách đặt, hủy rồi đặt lại cùng giờ ở lượt sau thì khóa khác.
- Lỗi: câu tiếng Việt của CRM nếu có (CRM viết sẵn, không tên số), không thì một câu theo loại lỗi; 401/403 là "cổng
  chưa mở", 5xx hay mất kết nối là "CRM đang không trả lời".
- `ToolContext` không có loại chat (nhóm hay 1-1), nên chặn bàn lịch trong nhóm hiện **chỉ là luật mềm** trong
  `AGENTS.md` (ghi rủi ro ở HANDOFF 15). Bước 6 thêm `conversation_id`/loại chat cho tin chủ động thì chặn cứng luôn.

**Bật và hướng dẫn:** thêm tool và plugin vào `agents/clinic/agent.toml`. `AGENTS.md` (luật mềm): nhắc lại ngày giờ, tên,
số, đợi khách đồng ý trước khi đặt hay dời; xin phép trước khi lưu số và hỏi có muốn nhận nhắc lịch qua Zalo không (Nghị
định 13/2023, 91/2020); câu trả lời không rõ ("ừ") thì hỏi lại, không tự xác nhận; khách muốn hủy thì hỏi có hẹn giờ
khác không; không hứa bác sĩ cụ thể; chính sách hủy muộn lấy từ kho tri thức.

### 3.4 CRM báo lịch cho agent (bước 2 phía CRM, bước 4 phía agent)

```
CRM: đặt / dời / hủy / xác nhận / vắng / hoàn tất lịch của người đã nối  (hoặc đổi đồng ý nhận nhắc)
  → ghi một dòng vào clinic.agent_event, CÙNG GIAO DỊCH với thay đổi
  → khi commit: đánh thức worker "agent-events" trong AppLifecycle
  → worker ký (HMAC) và POST /v1/hooks/crm/events sang agent; 2xx thì đánh dấu đã giao, lỗi thì hẹn thử lại
Agent: kiểm chữ ký, bỏ trùng, ghi vào bảng nhắc của mình, đánh thức đồng hồ hẹn giờ
  → ngủ tới mốc gần nhất → thức: kiểm lại điều kiện → gửi tin nhắc qua đường chủ động
(đối soát: lúc plugin khởi động và mỗi 24 giờ, agent gọi GET /reminders?hours=48 MỘT lần để vá sự kiện bị lỡ)
```

**Bảng** `clinic.agent_event` (migration `0003`, outbox của CRM): `id` bigserial, `event_id` uuid (khóa duy nhất),
`kind`, `payload` jsonb, `created_at`, `attempts`, `next_attempt_at`, `delivered_at`, `failed_at`, `last_error`.

**Hai loại sự kiện** (payload tối thiểu):
- `appointment.changed`: `appointment_id`, `channel`, `external_id`, `starts_at`, `duration_min`, `status`, `version`,
  `messages_consent`, `actor_type` (user | agent), `occurred_at`. Chỉ ghi khi bệnh nhân của lịch có dòng
  `patient_channel`.
- `person.changed`: `channel`, `external_id`, `messages_consent`, `occurred_at`. Ghi khi đồng ý nhận nhắc đổi (cổng agent
  `PUT contacts` hoặc nhân viên ghi `consent.record` loại `messaging`).

**Chỗ ghi sự kiện (cùng giao dịch):** `book_in_session`, `update_appointment`, `transition` (mọi verb), dời lịch của cổng
agent, `record_consent` (loại `messaging`) và `save_contact`. Một hàm `agent_events.record_*(session, …)` gọi ở đó;
test cấu trúc (`test_agent_events_calls.py`, đọc mã bằng AST) kiểm chỗ tạo hoặc dời lịch chính xác là bốn nơi đã biết
và mỗi nơi đều gọi hàm ghi; chỗ thêm dòng `consent` chính xác là hai nơi.

**Worker `agent-events`** (trong `AppLifecycle`, cạnh `crm-rules`):
- Đánh thức bằng `asyncio.Event`: hàm ghi sự kiện gắn một hàm `after_commit` vào phiên (`agent_events.set_waker`), nên
  worker chỉ thức sau khi giao dịch đã commit; không quét theo chu kỳ khi bảng rỗng (chờ không hạn). Khi còn dòng chờ
  thử lại thì ngủ tới `min(next_attempt_at)`. **Khác bản đầu:** không cần thêm người nghe cho `appointment_events`.
- Giao theo thứ tự `id`; thất bại thì `attempts+1`, `next_attempt_at = now + 30s·2^attempts` (tối đa 1 giờ); sau 8 lần
  đánh dấu `failed_at` và dừng (đối soát bù). Mỗi lần giao có `timeout` 5 giây; mọi lỗi mạng không làm worker chết.
- (Đã làm.) Bảng `agent_event` dùng một lớp nền riêng (`OutboxBase`) vì bộ chặn audit chỉ canh dữ liệu phòng khám; việc
  đánh dấu đã giao không phải thay đổi phòng khám nên không cần dòng audit. Dòng sự kiện chỉ được THÊM, trong giao dịch
  của thay đổi mà nó báo (giao dịch đó có audit).
- Ký mỗi lần giao bằng **khóa Ed25519 sẵn có của CRM** (khóa đang ký token SSO, công khai ở JWKS): thân yêu cầu là một
  JWT `iss = pema-clinic`, `aud = pema-agent-events` (khác `aud = pema-agent` của SSO), `exp` 2 phút, `jti` = `event_id`,
  sự kiện trong claim `event`. Địa chỉ đích `PEMA_AGENT_EVENTS_URL` (trong stack: `http://agent:8088/v1/hooks/crm/events`).
  Không đặt biến thì worker tắt và `agent_event` không ghi. Không còn bí mật dùng chung `PEMA_AGENT_EVENTS_SECRET`.
- Dòng đã giao được xóa sau 7 ngày (nhóm vào việc dọn dữ liệu có sẵn, `retention`).

**Route nhận ở agent** (`hooks`, `POST /v1/hooks/crm/events`): kiểm JWT bằng JWKS của CRM (chữ ký, `iss`,
`aud = pema-agent-events`, hạn); **plugin `sso` phải từ chối token có `aud` này** (test), để một sự kiện không bao giờ
thành phiên quản trị; bỏ `event_id` đã nhận; `appointment.changed` chỉ ghi khi `version` lớn hơn bản đang giữ; `person.changed` chỉ ghi khi
`occurred_at` mới hơn. Trả 200 ngay sau khi ghi (không gọi model, không gọi CRM). Chỉ route này nhận; nó **không trả
dữ liệu** về CRM.

**Bảng của plugin** (migration plugin, schema `agent_rt`):
- `crm_reminder`: `appointment_id` (khóa), `channel`, `external_id`, `starts_at`, `status`, `version`,
  `messages_consent`, `changed_at` (lần đổi cuối do người, không do agent: xem 3.5), `last_event_id`.
- `crm_reminder_sent`: (`appointment_id`, `starts_at`, `mark`) **khóa duy nhất** = khóa chống nhắc trùng.
- `crm_person`: (`channel`, `external_id`) → cuộc chat để gửi.

**Đã làm (bước 5, 2026-10-21), khác chữ ở trên:**
- **Không cần bảng "sự kiện đã nhận".** Mọi sự kiện là trạng thái: lịch chỉ ghi khi `version` cao hơn, đồng ý nhận nhắc
  chỉ ghi khi `occurred_at` mới hơn; sự kiện lặp, đến muộn hay đảo thứ tự đều không đổi gì sai.
- **Đồng ý nhận nhắc nằm ở `crm_person`** (theo người), không ở `crm_reminder`: cả hai loại sự kiện đều cập nhật nó
  theo quy tắc "mới nhất thắng".
- **`changed_at` = lúc GIỜ của lịch được đặt** (đặt mới hoặc dời), bất kể ai làm; đổi trạng thái (xác nhận, hủy) giữ
  nguyên. Nhờ vậy khách xác nhận qua tin nhắc không làm bỏ mốc nhắc sau, còn lịch đặt sát giờ thì bỏ mốc đã qua.
- **Trả lời:** 200 `applied`; loại sự kiện lạ 200 `ignored` (CRM mới hơn không làm outbox thử lại vô ích); token sai
  401; không lấy được JWKS 503 (CRM thử lại); sự kiện hỏng 422. Route chưa đánh thức job nhắc: bước 6 thêm.
- `crm_person.conversation_id` đã có cột (trống), bước 6 điền.

### 3.5 Nhắc hẹn: đồng hồ của agent

**Job `crm-reminders`** (`ctx.register_job`): vòng lặp "ngủ tới mốc gần nhất", không gọi CRM.
- Mốc *m* (24 giờ, 3 giờ) của một lịch đến hạn lúc `due = starts_at − m`.
- Ngủ `min(due kế tiếp, 1 giờ)` hoặc tới khi route nhận sự kiện đánh thức (mốc 1 giờ chỉ là lưới an toàn cục bộ, không
  chạm CRM).
- Thức dậy, với mỗi mốc đã đến hạn, **đọc lại dòng cục bộ** rồi mới quyết:

| Điều kiện | Kết quả |
|---|---|
| trạng thái không còn `booked`/`confirmed` (hủy, vắng, xong), hoặc đã qua giờ khám | bỏ, không bao giờ nhắc nữa |
| `messages_consent` khác true | bỏ |
| mốc 24 giờ mà lịch đã `confirmed` | bỏ mốc này |
| `changed_at ≥ due` (lịch vừa đặt hoặc vừa dời sau mốc) | bỏ mốc này; nếu dời giờ, các mốc của giờ mới tính lại |
| còn dưới 6 giờ (mốc 24 giờ) hoặc dưới 30 phút (mốc 3 giờ) tới giờ khám | bỏ |
| đang giờ yên lặng | hoãn tới hết giờ yên lặng, kiểm lại điều kiện rồi mới gửi |
| người này đã nhận 2 tin nhắc hôm nay | bỏ |
| `crm_reminder_sent` đã có (lịch, giờ, mốc) | bỏ |

- Đủ điều kiện thì **ghi dòng `crm_reminder_sent` trước, gửi sau** (chống nhắc trùng kể cả khi chết giữa chừng; đổi lại
  gửi lỗi thì mốc đó mất, không thử lại, ghi dấu vết).
- **Đường gửi:** lõi cho plugin dùng chung đường gửi chủ động `ctx.proactive` (tách `DispatcherOutbox` khỏi
  `FollowUp`: nhận `channel`, `conversation_id`, `user_id`, `message_id`, chỉ dẫn; tên lõi không nhắc gì tới CRM).
  Chỉ dẫn chứa sẵn **giờ và ngày do code định dạng** kèm mẫu câu; model chỉ thêm lời chào, không được đổi giờ.
- **Cần xác minh lúc làm bước 5:** `ToolContext` không có `conversation_id`. Tìm cuộc chat qua phiên (như vòng chăm sóc
  lại đang làm) và ghi vào `crm_person`. Người không có dòng `crm_person` thì không gửi được: ghi dấu vết.
- Tin nhắc vào lịch sử phiên như mọi tin chủ động, nên khi khách trả lời agent biết đang nói lịch nào và đi theo đường A.

**Đối soát:** lúc plugin khởi động và mỗi 24 giờ, một lần `GET /reminders?hours=48`; ghi các lịch trả về (cùng quy tắc
`version`); lịch cục bộ trong 48 giờ tới mà CRM không còn trả (đã hủy hoặc đã đổi ra ngoài khung) thì đánh dấu `gone`.

### 3.6 Vòng lặp: bảy câu cho từng vòng

Theo `IDEAS-agent-loops.md` mục 1. Bốn vòng ngoài của kế hoạch này (vòng trong `run_turn` và vòng giữa `Dispatcher`
không đổi):

| | **V1 Nhắc hẹn** (agent) | **V2 Giao sự kiện** (CRM → agent) | **V3 Đối soát** (agent → CRM) | **V4 Khách trả lời tin nhắc** |
|---|---|---|---|---|
| Kích hoạt | đồng hồ tới mốc, hoặc sự kiện làm đổi mốc | commit một thay đổi lịch hoặc đồng ý nhận nhắc; hẹn thử lại | khởi động plugin; mỗi 24 giờ | tin của khách (lượt chat bình thường) |
| Quan sát | dòng cục bộ: trạng thái, `version`, đồng ý, `changed_at`, đã nhắc chưa | dòng outbox chưa giao, lần thử | danh sách lịch 48 giờ từ CRM | lịch sử phiên (có tin nhắc) |
| Hành động | code: kiểm điều kiện, định dạng giờ; model: lời chào | POST có chữ ký | ghi/đánh dấu `gone` bằng cùng quy tắc `version` | model hiểu ý; tool đổi lịch có `Idempotency-Key` |
| Kiểm | `crm_reminder_sent` (khóa duy nhất) | 2xx của agent; agent kiểm chữ ký và `event_id` | không | CRM trả lịch sau khi đổi; `version` chặn lịch vừa đổi |
| Dừng | mỗi mốc ≤ 1 lần; lịch hủy/xong/qua giờ thì hết | giao xong hoặc 8 lần rồi `failed_at` | một lần mỗi kỳ | 2 lịch sắp tới, 3 lần dời mỗi lịch |
| Giới hạn và tắt | 2 tin nhắc mỗi người mỗi ngày; hạn mức ngày và công tắc tắt khẩn của bridge; `reminders.enabled` | bỏ biến `PEMA_AGENT_EVENTS_URL` thì tắt hẳn; thời gian chờ 5 giây | đi cùng `reminders.enabled` | 10 lần ghi mỗi người mỗi giờ; công tắc cổng (bỏ khóa công khai thì 404); log của `crm-signer` |
| Người trong vòng | (để sau: báo lễ tân khi hủy muộn, HANDOFF 12) | danh sách `failed_at` cho quản trị (để sau) | không | (để sau) |

### 3.7 Những vòng có thể tự quay, và cách chặn (mỗi dòng một test)

| Vòng tự quay | Ví dụ | Chặn bằng |
|---|---|---|
| **Vọng lại** | khách xác nhận qua chat → CRM báo "lịch đổi" → agent hẹn nhắc lại → nhắn khách nữa | sự kiện chỉ cập nhật dòng cục bộ, **không tự sinh tin**; tin chỉ sinh từ mốc giờ (V1). Xác nhận không đổi khóa `crm_reminder_sent`. Sự kiện `actor_type = agent` không đặt `changed_at`. |
| **Trùng sự kiện** | worker giao lại vì mạng chập chờn | `event_id` bỏ trùng; `version` cũ hơn thì bỏ; sự kiện mô tả trạng thái nên giao hai lần ra cùng kết quả |
| **Bão thử lại** | agent chết, CRM thử lại liên tục | giãn cách 30s·2^n, trần 1 giờ, 8 lần rồi `failed_at`; đối soát bù |
| **Nhắc trùng sau khi chết giữa chừng** | agent chết sau khi gửi trước khi ghi | ghi `crm_reminder_sent` trước khi gửi (chấp nhận mất tin hơn là trùng) |
| **Nhắc người đã hủy** | khách hủy 10:00, tin 11:00 vẫn chạy | thức dậy đọc lại dòng cục bộ (sự kiện hủy đã cập nhật); đã hủy/qua giờ thì bỏ |
| **Nhắc người đã rút đồng ý** | khách nhắn "đừng nhắc nữa" | `person.changed` cập nhật `messages_consent`; mốc đọc lại cờ trước khi gửi |
| **Hai bot nói chuyện** | Zalo của khách trả lời tự động, agent trả lời lại mãi | tin nhắc chỉ sinh từ mốc giờ, không từ trả lời; trần 2 tin nhắc mỗi người mỗi ngày. **Trần số lượt agent trả lời mỗi khách mỗi giờ là việc của lõi (Dispatcher), chưa có: ghi HANDOFF 13.** |
| **Hai vòng chồng nhau** | chăm sóc lại và nhắc hẹn cùng nhắn một khách | cùng đi qua `ctx.proactive` và hạn mức ngày của bridge; **vòng chăm sóc lại bỏ qua khách có lịch sắp tới: để sau (HANDOFF 13)**; hiện chăm sóc lại tắt mặc định |
| **CRM chết hoặc chậm** | giao sự kiện treo giao dịch của quầy lễ tân | worker chạy ngoài giao dịch của lịch (sau commit), thời gian chờ 5 giây, lỗi không ném ra ngoài |
| **Sự kiện giả mạo** | ai đó gọi route nhận từ trong mạng | JWT ký bằng khóa riêng của CRM (agent chỉ có khóa công khai), `aud` riêng, hạn 2 phút, `jti` bỏ trùng, cổng không mở ra ngoài máy; sai thì 401 |

### 3.8 Luật mới (thay chữ trong `.claude/rules/agent-crm-boundary.md`)

- **L2:** **Tiến trình agent không giữ khóa, mật khẩu hay tài khoản nào của CRM.** Mọi yêu cầu tới CRM đi qua
  `crm-signer`, dịch vụ duy nhất giữ khóa riêng ký JWT ngắn hạn; CRM chỉ giữ khóa công khai và chỉ mở nhóm route
  `/api/v1/agent-gateway` với sáu quyền `agent.*`. API không nhận token `aud = pema-agent` làm phiên. Chiều ngược lại:
  CRM ký sự kiện bằng khóa riêng của CRM (`aud = pema-agent-events`) và chỉ gửi tới **một** route của agent; route đó chỉ
  nhận, không trả dữ liệu, và token sự kiện không bao giờ mở được phiên của agent.
- **L3:** Không schema, view, hàm SQL hay role riêng cho agent trong `pema`. `clinic.patient_channel` và
  `clinic.agent_event` là dữ liệu CRM; agent chạm chúng gián tiếp qua các endpoint trên.
- **L4:** Dữ liệu phòng khám vào agent qua bốn đường: tài liệu đã duyệt, danh sách giờ trống, lịch sắp tới **của chính
  người đang chat**, sự kiện lịch (mã, kênh, ID, giờ, trạng thái) của người đã nối. Agent ghi vào CRM đúng ba thứ:
  hồ sơ liên hệ (tên, số, đồng ý nhận nhắc), lịch mới, đổi trạng thái hoặc giờ của lịch thuộc người đang chat. Không
  tool tra bệnh nhân khác, đơn, tài chính.
- **L6 (thêm một câu):** container agent chỉ ở mạng nội bộ; mọi kết nối ra internet (model, Zalo, tool web) đi qua proxy
  đi ra `egress`, ngoài `netguard` của tool web. Danh sách đích được phép do chủ duyệt.
- **L7 (mới): danh sách tool của từng profile là danh sách được duyệt.** Thêm tool, hoặc bật `agent_writes`, là đổi kế
  hoạch, chủ duyệt; test giữ danh sách đỏ cho tới khi được sửa có chủ ý. Không bao giờ có tool đọc file, chạy lệnh hay
  chạy mã trong tiến trình agent.
- L1, L5 giữ nguyên. Mở thêm endpoint, quyền hay loại sự kiện nào thì cần kế hoạch mới, chủ duyệt.

### 3.9 `crm-signer`: dịch vụ giữ khóa và ký yêu cầu (ẩn credential)

```
agent (không khóa) ──HTTP──► crm-signer (giữ khóa riêng) ──Bearer JWT──► api /agent-gateway (giữ khóa công khai)
```

- **Một ứng dụng nhỏ mới** `apps/crm-signer` (Python, `httpx` + Starlette, bốn file nhỏ; **đã viết 2026-10-21**), container riêng,
  cổng `8090` chỉ trong mạng nội bộ. Không DB, không model, không tool, không gì khác.
- **Việc của nó:** nhận yêu cầu ở `/agent-gateway/<đường>`, kiểm **phương thức + đường** có trong danh sách cố định
  (đúng 8 route của mục 3.2), ký một JWT mới cho mỗi yêu cầu (`iss`, `aud`, `exp` **1 phút** (mỗi token một lần gọi nên ngắn hơn mức 2 phút CRM nhận), `jti`, `scope` = đúng quyền
  của route đó), chuyển tiếp thân và các header cho phép (`Content-Type`, `Idempotency-Key`, `X-Request-Id`), trả lại
  nguyên văn kết quả của CRM. Đường lạ thì 404 mà không gọi CRM. Không theo chuyển hướng.
- **Khóa riêng:** file `0600` trong volume chỉ `crm-signer` gắn (như cách `agent_token.py` giữ khóa của CRM); tạo một lần
  bằng lệnh của chính nó (`crm-signer keygen`), in khóa công khai để dán vào `PEMA_AGENT_GATEWAY_PUBLIC_KEYS` của API. Đổi
  khóa: tạo khóa mới, thêm khóa công khai mới vào API (hai khóa cùng hợp lệ), đổi file, bỏ khóa cũ.
- **Giới hạn và log độc lập với agent:** giới hạn tần suất riêng, một dòng log mỗi yêu cầu (đường, mã trả về, thời gian;
  không thân, không tên, số). Agent bị chiếm vẫn gọi được qua đây **trong lúc bị chiếm**, nhưng không mang được khóa đi,
  và mọi lần gọi có dấu vết ở chỗ agent không sửa được.
- **Container:** `read_only`, `cap_drop: [ALL]`, `no-new-privileges`, người dùng thường; ra được đúng `api:8000`.
- **Trong khung vòng của chủ (IDEAS-agent-loops.md mục 5):** `crm-signer` không phải một vòng, nó là "thẻ quyền nhân viên đeo" khi dùng công cụ CRM: không `trigger`, không `stop`; giới hạn tần suất của nó là phanh chung cho mọi vòng đi qua. Test đối chiếu `test_the_route_list_is_the_crm_gateway` giữ hai bên (8 route của CRM, 6 quyền) không lệch.
- **Giới hạn thật:** `crm-signer` vẫn tin `channel`/`external_id` mà agent gửi (CRM không xác thực được người Zalo). Nó
  giải quyết việc *lộ khóa*, không giải quyết việc *agent bị chiếm tự khai người khác* trong lúc bị chiếm.

### 3.10 Cứng hóa agent và hạn chế internet

**a. Test khóa (làm được ngay, không cần Docker):**
- danh sách tool của profile `clinic` đúng bằng một tập cố định trong test (L7);
- `agent_writes` của plugin `skills` tắt trong profile `clinic`;
- không tool nào đăng ký trong lõi hay plugin có tên chứa `shell`, `exec`, `file`, `python`, `code` (lưới thô, bổ sung
  cho danh sách);
- dịch vụ `agent` trong `docker-compose.yml`: biến môi trường thuộc danh sách cho phép (không `PEMA_JWT_SECRET`, không mật
  khẩu của CRM, không khóa cổng); có `read_only`, `cap_drop: [ALL]`, `no-new-privileges`; chỉ thuộc mạng `internal`.

**b. Compose (cần build lại và thử trên stack):**
- `agent`: `read_only: true`, `tmpfs: /tmp`, chỗ ghi duy nhất là volume `/data`; `cap_drop: [ALL]`;
  `security_opt: [no-new-privileges:true]`. **Cần kiểm lúc làm:** cầu nối Zalo (Node, chạy trong container agent) ghi
  vào đâu ngoài `/data`.
- Mạng `agent-internal` (`internal: true`, không ra internet): `agent`, `crm-signer`, `egress`, `postgres`, `api`,
  `frontend`. `agent` **chỉ** thuộc mạng này. `api` vẫn thuộc thêm mạng của nó; agent với tới `api:8000` nhưng không có
  credential nào, nên chỉ gặp 401/404 (như hôm nay).

**c. Proxy đi ra `egress`** (container riêng, phần mềm có sẵn: Squid hoặc tinyproxy, chỉ cấu hình, không viết code):
- agent đặt `HTTPS_PROXY`/`HTTP_PROXY=http://egress:3128`, `NO_PROXY=crm-signer,postgres,api,localhost`;
- **giai đoạn 1 (chủ đã gác danh sách tên miền): chỉ ghi log** mọi đích, không chặn; sau một thời gian chạy thật, đọc
  log ra danh sách đích thật sự cần;
- giai đoạn 2 (khi chủ chốt danh sách): chặn mọi đích ngoài danh sách; luôn chặn dải mạng riêng và `169.254.169.254`.
- **Cần kiểm trước khi làm:**
  1. **zca-js có đi qua proxy được không** (HTTP và WebSocket tới Zalo). Nếu không: tách cầu nối Zalo ra container riêng
     được ra internet thẳng, agent nói chuyện với nó qua mạng nội bộ (giao thức ký HMAC hiện có giữ nguyên).
  2. client model, embedding, TypeSafe dùng `httpx` có đọc `HTTPS_PROXY` không (`trust_env`), hay phải truyền proxy.
  3. `netguard` tự phân giải DNS và nối vào IP đã kiểm; qua proxy thì proxy phân giải. Phải giữ hàng rào SSRF (T5) đúng:
     hoặc `web_fetch` đi thẳng như hôm nay và chỉ phần còn lại qua proxy, hoặc proxy chặn thêm dải mạng riêng. Chọn khi
     làm, T5 phải xanh.
- **Chưa làm trong kế hoạch này:** khóa model, embedding, TypeSafe vẫn nằm (mã hóa) trong DB của agent và tiến trình
  agent đọc được. Chuyển chúng vào proxy là bước sau (HANDOFF mục 14).

## 4. Test giữ luật (đỏ là không merge)

**CRM (`apps/api/tests`)**
- **T3** giữ nguyên. **T6 (đã viết):** khóa máy gọi route cũ → 401; cookie nhân viên gọi cổng → 401; khóa sai → 401; không
  đặt băm → 404 (sau bước 1b: không đặt khóa công khai → 404). **T7 (đã viết):** `AGENT_PERMISSIONS` đúng sáu quyền, không vai trò nhân viên nào có. **T8 (đã viết):**
  người A không xem, xác nhận, dời, hủy được lịch của người B (404).
- Đã viết cho cổng: giờ trống (giờ nghỉ, đủ bác sĩ thì hết chỗ, lịch hủy trả chỗ, không lộ tên), liên hệ (chuẩn hóa số,
  lần hai không sửa, trùng số vẫn hồ sơ mới, đồng ý ghi một dòng mỗi lần đổi), đặt (409 khi chưa có liên hệ hoặc hết
  chỗ, `Idempotency-Key`, tối đa 2 lịch), dời (tối đa 3 lần, một lần mỗi khóa), xác nhận và hủy, đối soát, audit
  (actor `agent`, không có tên, số), giới hạn tần suất.
- **Outbox (bước 2):** mỗi nơi đổi lịch (5 nơi ở 3.4) để lại đúng một sự kiện trong cùng giao dịch, và hoàn tác giao dịch
  thì không để lại; lịch của người chưa nối không sinh sự kiện; `person.changed` khi đổi đồng ý; payload không có tên,
  số; **test cấu trúc**: mọi nơi sửa `Appointment` đều gọi hàm ghi sự kiện; worker: giao đúng thứ tự, lùi thử lại, dừng
  sau 8 lần, lỗi mạng không làm worker chết, JWT sự kiện có `aud = pema-agent-events`; bỏ biến thì không ghi.
- **Bước 1b (JWT):** token hết hạn, sai `aud`, sai `iss`, ký bằng khóa lạ, thiếu `scope` của route, `jti` dùng lại → 401
  hoặc 403; hai khóa công khai cùng hợp lệ khi đổi khóa; token SSO (`aud = pema-agent`) không mở được cổng.

**`crm-signer` (`apps/crm-signer/tests`)**
- Đường hay phương thức ngoài danh sách → 404, không gọi CRM; mỗi route được ký đúng `scope`; header lạ (`Authorization`
  do agent gửi, `Cookie`) bị bỏ; không theo chuyển hướng; khóa riêng không xuất hiện trong log hay kết quả; thiếu file
  khóa thì không khởi động.

**Agent (`apps/agent/tests`)**
- **T4 giữ nguyên ý:** profile chỉ chứa địa chỉ API ở `sso.jwks_url`; `crm.base_url` trỏ vào `crm-signer`, không vào
  `api`; không chuỗi nào trông như khóa hay bí mật.
- Plugin `crm` với `crm-signer` giả: tham số tool không có trường người; danh tính từ `ToolContext`; lỗi thành câu đọc
  được; plugin không đọc biến môi trường nào chứa khóa.
- Route nhận sự kiện: JWT sai chữ ký, sai `aud`, quá hạn, thiếu → 401; `event_id` trùng bỏ; `version` cũ bỏ;
  `person.changed` đổi cờ. **Plugin `sso` từ chối token `aud = pema-agent-events`.**
- **T9 (mới, mục 3.10a):** danh sách tool của `clinic` đúng tập được duyệt; `agent_writes` tắt; không tool tên nguy hiểm;
  dịch vụ `agent` trong compose: biến môi trường theo danh sách cho phép, `read_only`, `cap_drop`, `no-new-privileges`,
  chỉ mạng `agent-internal`.
- Job nhắc (đồng hồ giả), mỗi hàng của mục 3.5 và mỗi dòng của mục 3.7 một test: đúng mốc gửi một lần; dời giờ nhắc lại
  theo giờ mới; xác nhận không nhắc lại; đặt hoặc dời sau mốc không gửi; `confirmed` bỏ mốc 24 giờ; giờ yên lặng hoãn rồi
  gửi; quá sát giờ khám bỏ; rút đồng ý thì bỏ; hủy giữa chừng thì bỏ; trần 2 tin mỗi ngày; chết giữa chừng không nhắc
  trùng; gửi lỗi không thử lại; sự kiện do agent gây ra không sinh tin; `reminders.enabled` tắt thì không gửi.
- `ctx.proactive`: plugin gửi được; tin mang `PROACTIVE`; tên lõi không nhắc CRM (`test_the_core_names_no_chat_platform`
  vẫn xanh); các test `follow_up` vẫn xanh.
- **T1, T5** giữ nguyên.

## 5. Các bước

| Bước | Việc | Xong khi |
|---|---|---|
| 0 | **Cứng hóa, phần test** (mục 3.10a, T9): làm được ngay, độc lập với mọi bước khác | T9 xanh |
| 1 | CRM: cổng agent (đã viết): migration `0002`, quyền, khóa máy, chuẩn hóa số, 8 route, openapi/types | **22 test cổng qua trên DB tạm (đã chạy).** Còn chạy cả bộ test `apps/api` và `contracts` (chưa chạy), `ruff`/`pyright` sạch (đã sạch) |
| 1b | **(đã làm)** CRM: đổi xác thực cổng từ khóa băm sang JWT Ed25519, kiểm bằng khóa công khai (mục 3.2) | Test 1b và 22 test cổng xanh, cả bộ `apps/api` xanh |
| 2 | **(đã làm 2026-10-20, bộ test đầy đủ xanh: 1112 qua)** CRM: outbox: migration `0003`, hàm ghi sự kiện ở 5 nơi, listener nhiều người nghe, worker `agent-events`, JWT sự kiện ký bằng khóa có sẵn của CRM, biến `PEMA_AGENT_EVENTS_URL`, dọn dòng cũ | Test outbox mục 4 xanh, cả bộ `apps/api` xanh |
| 3 | **(đã làm 2026-10-21)** `crm-signer`: ứng dụng nhỏ (`apps/crm-signer`, Starlette), `keygen`, danh sách 8 route, ký JWT, chuyển tiếp, log, giới hạn 300/phút, Dockerfile, dịch vụ `crm-signer` trong compose (profile `agent`, `read_only`, `cap_drop ALL`), `PEMA_AGENT_GATEWAY_PUBLIC_KEYS` vào `.env` và `api` | 24 test `crm-signer` xanh, test cổng và sự kiện xanh trên DB tạm; **chưa build Docker** |
| 4 | **(đã làm 2026-10-21)** Agent: plugin `crm`: client gọi `crm-signer`, 7 tool, profile, `AGENTS.md`, T4, T9. **`crm_person` dời sang bước 6** (cần `conversation_id`, chỉ dùng cho tin chủ động) | 18 test plugin, T4, T9 xanh |
| 5 | **(đã làm 2026-10-21)** Agent: route nhận sự kiện `POST /v1/hooks/crm/events` (JWKS của CRM, `aud` riêng), `sso` từ chối `aud` sự kiện (test), bảng `crm_reminder`, `crm_person`, `crm_reminder_sent` (migration plugin `0001_crm.sql`), `PEMA_AGENT_EVENTS_URL` vào compose (để trống) | 15 test route và trạng thái, 2 test Postgres, `sso`, T4 xanh |
| 6 | Lõi và nhắc hẹn: `ctx.proactive` (tách `DispatcherOutbox`), job `crm-reminders`, đối soát; tìm `conversation_id` cho người chat | Test job và `ctx.proactive` xanh; test `follow_up` vẫn xanh |
| 7 | **Cứng hóa, phần compose** (mục 3.10b): `read_only`, `tmpfs`, `cap_drop`, `no-new-privileges`, mạng `agent-internal`; kiểm chỗ ghi của cầu nối Zalo | Stack chạy, agent trả lời được qua Zalo, T9 xanh với compose mới |
| 8 | **Proxy đi ra, giai đoạn 1** (mục 3.10c): **kiểm zca-js qua proxy trước**, rồi dựng `egress` chỉ ghi log, đặt `HTTPS_PROXY` cho agent; T5 vẫn xanh | Log có đủ đích; Zalo, model, kho tri thức vẫn chạy |
| 9 | Luật và tài liệu: `agent-crm-boundary.md` (L2-L4, L6, L7, T6-T9), `GUIDE-agent-harness.md`, `infra/README.md` (sinh khóa `crm-signer`, khóa công khai cho API, đổi khóa), HANDOFF | Đọc lại khớp code |
| 10 | Thử thật (sau khi chủ build lại Docker): chat Zalo hỏi giờ, lưu số, đặt, xem lại, dời, hủy; đặt lịch cách ~3 giờ 20 phút, bật nhắc, chờ tin nhắc, trả lời "đồng ý"; tắt agent, đổi lịch trên CRM, bật lại, xem sự kiện được giao bù; xem log của `crm-signer` và `egress` | Ghi kết quả vào mục 7 |

Bước 1b, 2 và 6 đụng lõi hoặc migration nên chạy bộ test đầy đủ của phần bị đụng (`apps/api`; `agent-core` +
`apps/agent`). Bước 7 và 8 đổi cách stack chạy: làm trên máy thử, có đường quay lại (bỏ các dòng compose mới).
Giai đoạn 2 của proxy (chặn theo danh sách) chờ chủ chốt danh sách tên miền.

## 6. Rủi ro

- **Không lễ tân xác nhận, không báo nhân viên (chủ chọn):** lịch vào thẳng `booked`; khách đùa hay bị lừa đặt có thể
  chiếm giờ; hủy muộn không ai được báo. Giảm bằng tối đa 2 lịch mỗi người và giới hạn tần suất (HANDOFF 12).
- **Tin nhắc do model viết** (mục 3.5): giờ do code định dạng nằm sẵn trong chỉ dẫn, nhưng model vẫn có thể chép sai;
  cần thử thật. Đường gửi nguyên văn để sau (HANDOFF 13).
- **Mất sự kiện:** CRM chết, mạng đứt, agent tắt lâu. Outbox giữ và giao bù; quá 8 lần thì `failed_at` và đối soát hằng
  ngày bù tối đa 48 giờ tới. Lịch dời hoặc hủy ngay trước mốc trong lúc đường giao đang hỏng vẫn có thể nhận tin theo
  dữ liệu cũ.
- **Nhắc mất thay vì trùng:** ghi dấu trước khi gửi, nên agent chết đúng lúc đó thì mốc ấy không được nhắc.
- **Phụ thuộc đồng hồ và múi giờ:** dùng `starts_at` có múi giờ; giờ yên lặng tính theo `Asia/Ho_Chi_Minh`.
- **Cửa mới vào agent:** route `hooks/crm/events`. Chỉ trong mạng Docker, kiểm chữ ký và thời gian, không trả dữ liệu;
  bí mật lộ thì kẻ có mạng nội bộ làm sai bảng nhắc (không đọc được gì, không tự gửi tin vì tin chỉ sinh từ mốc giờ
  của lịch thật trong bảng).
- **Zalo cá nhân nhắn chủ động** dễ bị đánh dấu spam (HANDOFF 7). Hạn mức ngày của bridge vẫn áp.
- **Hồ sơ trùng:** khách cũ chat Zalo lần đầu sẽ có hồ sơ mới và chưa được nhắc lịch cũ đặt qua điện thoại.
- **Giờ trống ước lượng:** tính theo số bác sĩ, không theo ca làm hay phòng; lịch agent đặt chưa có bác sĩ.
- **Agent bị chiếm vẫn gọi được CRM qua `crm-signer` trong lúc bị chiếm** (tạo hồ sơ, lịch giả, đổi lịch của người nó
  khai tên). Không mang khóa đi được; mọi lần gọi có log ở `crm-signer`. Khóa riêng của `crm-signer` bị lộ thì như cũ:
  tạo khóa mới, thay khóa công khai ở API.
- **Proxy đi ra làm hỏng agent:** chặn sai thì agent ngừng trả lời khách. Giai đoạn 1 chỉ ghi log; bước 7 và 8 làm trên
  máy thử, có đường quay lại.
- **SSRF qua proxy:** đổi đường ra của `web_fetch` có thể làm yếu `netguard`; T5 phải xanh trước khi bật.
- **Khóa model, embedding, TypeSafe vẫn trong tầm tiến trình agent** (mã hóa trong DB, agent giải mã được). Chưa xử lý
  trong kế hoạch này (HANDOFF mục 14).
- **Thêm hai dịch vụ phải vận hành** (`crm-signer`, `egress`): thêm chỗ có thể hỏng, cần healthcheck và cách xem log.
- **Không có dịch vụ trên lịch hẹn:** dịch vụ khách muốn chỉ nằm trong `note`.

## 7. Kết quả thử thật

(chưa có)
