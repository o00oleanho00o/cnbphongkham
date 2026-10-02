# Pema Agent — Architecture AI01

Đọc sau [MODULEMAP-AI01](MODULEMAP-AI01.md). Mô tả kiến trúc **đang có trong mã** (gốc: nhánh `feat/ai-agent-backend`, commit `1ce6cca`, 2026-10-02; **bản này theo nhánh `feat/single-tenant`: một hệ thống một phòng khám**, xem mục 14) và đích triển khai đã chọn. Phần chưa kiểm chứng được gắn nhãn thẳng; tổng hợp ở SCOPE-AI01 mục 8. Kiến trúc pilot của phòng khám nói chung (đa dịch vụ, tài chính) vẫn là [ARCH-PB01](../../docs/ARCH-PB01.md); tài liệu này chỉ là phần CSKH-agent và CRM phía server của nó, và **không thay thế** prototype web/KMP.

## 1. Cái nhìn container

```
 Bệnh nhân (Zalo)                                          Nhân viên (trình duyệt, qua Tailscale)
   │                                                            │
   ├─ Bot API ── polling ──────────────┐                        ▼
   │            └ webhook (HTTPS) ──┐  │                  Next.js (frontend, :3000)
   │                                │  │                        │  /api/* và /healthz: route handler
   └─ Zalo cá nhân ─► Cầu nối Node ─┤  │                        ▼          (cookie phiên cùng origin)
        (zca-js, tuỳ chọn, cờ tắt)  │  │          ┌─────────────────────────────────┐
        HMAC, chỉ loopback/nội bộ   ▼  │          │ api (FastAPI, uvicorn 1 worker) │  role DB: be_app
                              /webhooks/*────────►│ webhook · routers mỏng · gộp tin │
                                       │          │ (batcher) · vòng luật CRM · auth │
                                       │          └──────┬──────────────────┬───────┘
                                       │      TurnQueue (Redis)            │ SQL
                                       ▼                 ▼                 ▼
                                 ┌──────────────────────────┐   ┌─────────────────────────────┐
                                 │ worker (python -m        │   │ PostgreSQL 17 + pgvector    │
                                 │  pema.workers.main)      │   │  clinic.*  (CRM)            │
                                 │ lượt agent · scheduler · │◄──┤  clinic_agent.* (cửa duy nhất│
                                 │ KB ingest · polling bot  │   │   của agent vào phòng khám) │
                                 │ role DB: agent_worker    │   │  agent.*  (engine, KB, jobs)│
                                 └──┬──────────┬────────────┘   └─────────────────────────────┘
                                    │          │ Redis 7: hàng đợi lượt, khoá thread, gộp tin, khoá lịch
                          HTTP, nội bộ│          ▼
                                    ▼       Zalo (gửi tin, qua ChannelPort)
                   Ollama / llama-server trên PC GPU (RTX 3060 12 GB)
                   Qwen3-8B (chat) + bge-m3 (nhúng, 1024 chiều)
```

## 2. Kiến trúc tiến trình

| Tiến trình | Vai trò DB | Làm gì | Ghi chú |
|---|---|---|---|
| `api` | `be_app` | Nhận webhook Zalo, phục vụ route nhân viên, gộp tin (debounce) rồi đưa `TurnJob` vào Redis, chạy vòng luật CRM mỗi `PEMA_CRM_RUNNER_INTERVAL_SECONDS`, chạy tác vụ xóa theo thời hạn lưu **scope `clinic`** (`pema.retention`, mỗi `PEMA_RETENTION_INTERVAL_SECONDS`), duyệt và gửi tin đã duyệt | `uvicorn --factory pema.bootstrap:create_app --workers 1` (PLAN: 1 nhân CPU). Bộ gộp tin khôi phục các lô đang chờ khi khởi động |
| `worker` | `agent_worker` | Chạy lượt agent (`TurnWorker`, 4 lượt đồng thời mặc định, khoá theo thread), bộ lập lịch, nạp KB, nghe polling của account bot, các account cá nhân và quét tự chấp nhận kết bạn khi cờ bật, MCP manager, tác vụ xóa theo thời hạn lưu **scope `agent`** (`pema.retention`: thay lịch dọn ảnh và trace hằng ngày cũ), trả lại lượt của worker chết | Không có đặc quyền nào trên `clinic.*`; hook chính sách chạy **trong** tiến trình này |
| `zalo-personal-bridge` (Node 22, tuỳ chọn) | không dùng DB | Bọc `zca-js`: đăng nhập QR, nghe sự kiện, gửi tin; giữ thông tin đăng nhập chỉ trong bộ nhớ | Profile compose `bridge`; mặc định tắt (`PEMA_ZALO_PERSONAL_ENABLED=false` trong mã) |
| `frontend` (Next.js, `output: "standalone"`) | không dùng DB | UI; chỉ nói với origin của chính nó, route handler `src/app/api/[...path]/route.ts` và `healthz/route.ts` chuyển `/api/v1` và `/healthz` sang API ở địa chỉ `PEMA_API_INTERNAL_URL`, đọc **lúc chạy** ở mỗi yêu cầu (không build arg, không dựng lại ảnh khi đổi địa chỉ) | Profile compose `frontend` (và `proxy`) |
| `caddy` (reverse proxy, tuỳ chọn) | không dùng DB | Cửa công khai duy nhất: TLS, header bảo mật, trần thân yêu cầu; chỉ nối mạng `edge` nên không với tới Postgres, Redis hay cầu nối | Profile compose `proxy` + `docker-compose.proxy.yml`; mục 10 |
| `postgres` (pgvector pg17) | | `clinic`, `clinic_agent`, `agent`, `ctx` | scram, data checksums; cổng bind loopback mặc định |
| `redis` 7 | | Hàng đợi lượt (at-least-once, thời hạn nhìn thấy 20 phút), khoá thread, lô tin đang chờ, khoá bộ lập lịch, khoảng cách gửi theo account | mật khẩu, AOF, `noeviction` (hàng đợi và khoá không được bị đẩy ra) |
| Ollama / llama-server | | Chat và nhúng | Có thể là container (profile `ollama`) hoặc cài trực tiếp; **chỉ liên lạc qua HTTP** nên worker đặt cạnh DB và trỏ `LLM_BASE_URL` sang máy GPU |

Lý do tách `api` và `worker`: lượt agent có thể kéo dài nhiều phút (`LLM_TURN_TIMEOUT_MS` mặc định 900000), không được chặn webhook; worker chạy được trên máy GPU hoặc máy chủ; và nó **không cần** và **không có** quyền đọc bảng thô của phòng khám. Mỗi tiến trình chỉ nhận đúng một URL DB của vai trò mình (`PEMA_DATABASE_URL` cho api, `PEMA_WORKER_DATABASE_URL` cho worker); worker không giữ mật khẩu `be_app`.

Một account bot chỉ được **một** tiến trình nghe: chế độ `webhook` thì API nghe, chế độ `polling` thì worker nghe; tiến trình kia giữ đối tượng kênh chỉ để gửi. Tài khoản cá nhân vào bằng webhook có chữ ký HMAC từ cầu nối tới `/api/v1/webhooks/zalo-bridge/{account}` (không còn đoạn phòng khám: một bản cài là một phòng khám).

**Tác vụ xóa theo thời hạn lưu (`pema.retention`, thay cho lịch dọn ảnh/trace hằng ngày của bản dịch)**: một bộ chạy duy nhất, xóa từng lô nhỏ (`PEMA_RETENTION_BATCH_SIZE`, mặc định 500) cho phòng khám duy nhất của bản cài, chu kỳ `PEMA_RETENTION_INTERVAL_SECONDS` (mặc định 86400; 0 tắt vòng định kỳ, CLI vẫn chạy). Hai scope, mỗi tiến trình chỉ chạy scope hợp với vai trò DB của mình để không ai cần quyền rộng hơn: scope `agent` ở worker (`agent_worker`: `agent.history` và ảnh/mô tả của nó, `memories`, `usage` và `usage_steps` (trace), `job_runs`, `image_descriptions`, file ảnh trên volume); scope `clinic` ở API (`be_app`: `clinic.message` của hội thoại đã đóng rồi hội thoại rỗng, `auth_session` hết hạn, mã liên kết danh tính hết hạn hoặc đã dùng, `identity_link_attempt` cũ). Mặc định mã giữ dữ liệu lâm sàng và tin nhắn vô thời hạn (0 ngày) và chỉ cho dữ liệu thuần kỹ thuật một đời ngắn; thời hạn thật là quyết định của chủ phòng khám (SCOPE-AI01 mục 9). Không bao giờ xóa: `clinic.audit_log` (chỉ chèn, có trigger), bệnh nhân, lịch hẹn, đồng ý, `review_item` đang mở (mục đang mở cũng giữ lại cuộc trò chuyện và tin của nó). Mỗi lượt ghi MỘT dòng tóm tắt `retention.run` vào `clinic.audit_log` qua hàm `record_retention_run` (số đếm, không có nội dung). Chạy tay: `python -m pema.workers.retention [--dry-run] [--scope all|agent|clinic]` (tùy chọn `--clinic <id>` của bản đa phòng khám bỏ cùng gói ST-B) (`--dry-run` chỉ đếm; `make retention-dry-run`). Chạy lại và chạy từ hai nơi đều an toàn (khóa theo scope, `FOR UPDATE SKIP LOCKED`).

**Một phòng khám mỗi bản cài** (nhánh `feat/single-tenant`): mọi bảng vẫn giữ cột `clinic_id` nhưng nó là *mã cài đặt* cố định, không còn là khóa chọn phòng khám. Các vòng nền (bộ lập lịch, nạp KB, retention, vòng luật CRM, MCP) chạy một lượt cho phòng khám duy nhất, không còn lặp qua danh sách phòng khám (`ctx.list_active_clinic_ids()` đã bị xóa; shim Python trả `[mã cài đặt]` cho tới khi gói ST-B/ST-C bỏ hết chỗ gọi). Hệ quả: một worker cho một bản cài, không còn câu hỏi "một worker mỗi phòng khám hay chung". Muốn phục vụ thêm một phòng khám thì dựng một bản cài khác hẳn (server, CSDL, Redis, khóa riêng), mục 10.

## 3. Cơ sở dữ liệu

- **Schema**: `ctx` (hàm ngữ cảnh), `clinic` (CRM), `clinic_agent` (cửa của agent), `agent` (engine). Migration Alembic: `0001` clinic, `0002` agent (ghi cách ánh xạ mọi bảng SQLite gốc), `0003` clinic_agent; bổ sung `b1_0004`, `b2_0001`, `s_0004`, `p0001`; `g_0005` gộp đầu nhánh; `g_0006` ghim `search_path` của các hàm `SECURITY DEFINER`; `b1_0007_session_absolute_expiry` (cột `clinic.auth_session.absolute_expires_at` NOT NULL, hạn tuyệt đối của phiên, phiên cũ điền `created_at + 7 ngày`) và `h2_0007_retention` (chỉ mục theo tuổi cho các phép quét của tác vụ xóa, cộng hai hàm bên dưới) cùng nối sau `g_0006`, nên `h_0008_merge_heads` gộp lại; trên nhánh single-tenant còn `st_0009_single_tenant` (một phòng khám, bỏ RLS, mục dưới) là MỘT đầu duy nhất (`alembic heads` ra `st_0009_single_tenant`); chạy `alembic upgrade heads`.
- **Ràng buộc một dòng (`st_0009_single_tenant`)**: `clinic.clinic` có đúng MỘT dòng, do chính CSDL bảo đảm: cột `singleton boolean NOT NULL DEFAULT true` với `CHECK (singleton)` và `UNIQUE (singleton)` nên INSERT thứ hai thất bại; trigger chặn DELETE dòng đó (mã của nó là mã cài đặt, mọi bảng khác trỏ vào). Nâng cấp từ CSDL đã có từ hai phòng khám trở lên thì migration dừng, báo rõ (phải tách hoặc gộp trước). Hàm `clinic.ensure_clinic(name, slug, timezone, id)` tạo dòng đó idempotent (không đổi tên, không đổi mã, hỏi mã khác thì báo lỗi); chỉ role chủ chạy được. Migration gọi nó với `PEMA_CLINIC_NAME` (mặc định `Pema Clinic`), slug cố định `clinic` và `PEMA_CLINIC_ID` làm mã nếu có (không thì sinh một mã, một lần). `ctx.the_clinic_id()` (STABLE, SECURITY DEFINER, cả hai role gọi được) trả mã duy nhất và **báo lỗi khi bảng rỗng** (đóng khi hỏng, không trả "không có dòng" như thể CSDL trống); nó thay `ctx.current_clinic_id()` trong mười view `clinic_agent` và chín hàm definer, giữ `security_barrier`, quyền và `search_path ... pg_temp`. Đã xóa: 41 policy `clinic_isolation`, RLS trên mọi bảng `clinic.*` và `agent.*`, `ctx.current_clinic_id`, `ctx.resolve_clinic`, `ctx.list_active_clinic_ids`. Chi tiết hợp đồng: CONTRACTS-AI01 mục 10.
- **`clinic.*`** (21 bảng): `clinic`, `user_account`, `auth_session`, `patient`, `episode`, `treatment_plan`, `treatment_session`, `appointment`, `consent`, `conversation`, `message`, `review_item`, `message_template`, `crm_rule`, `crm_task`, `crm_activity`, `channel_setting`, `channel_identity`, `identity_link_code`, `identity_link_attempt`, `audit_log`.
- **`agent.*`**: `accounts`, `agents`, `contacts`, `friend_requests`, `threads`, `history`, `memories`, `image_descriptions`, `usage`, `usage_steps`, `jobs`, `job_runs`, `proactive_send_counters`, `kb_document`, `kb_chunk` (vector 1024, `tsvector` trên cột đã bỏ dấu), `agent_kb_document`, `mcp_servers`, `agent_mcp_servers`, `runtime_settings`, `channel_update_seen`.
- **Hai kho, hai mục đích**: `agent.history` là kho ngữ cảnh cho LLM; `clinic.message` là Inbox chính thức nhân viên đọc. Tầng kênh ghi cả hai. `review_item` ở `clinic.review_item`.
- **Role**: `be_app` (DML trên `clinic.*` và `agent.*`; `audit_log` chỉ chèn và đọc: không sửa, không xóa) và `agent_worker` (DML trên `agent.*`; đọc view `clinic_agent`; EXECUTE hàm `clinic_agent`; **không có gì trên `clinic.*`**). Từ `st_0009` **không còn RLS**: `be_app` và `agent_worker` đọc mọi dòng của bảng mà họ có quyền (chỉ có một phòng khám trong CSDL); cái còn lại để giới hạn họ là grant (và `agent_worker` không có gì trên `clinic.*`). `bootstrap-roles.sh` tạo role NOLOGIN, đặt mật khẩu từ môi trường (psql đọc bằng `\getenv`, không qua argv; `log_statement` tắt cho phiên đó), và mặc định thu hồi `CONNECT` của PUBLIC. Mật khẩu rỗng thì role vẫn NOLOGIN.
- **Không RLS, không ngữ cảnh phòng khám**: mọi bảng giữ `clinic_id` (khóa ngoại tới `clinic.clinic`, khóa kép vẫn dùng) như mã cài đặt; không còn policy, không còn `app.clinic_id`. Mở đơn vị công việc bằng `async with db.session() as s:` (đối số `clinic_id` cũ bị bỏ qua); mã cài đặt lấy bằng `get_installation_clinic_id(db)` (bộ nhớ đệm, rồi `PEMA_CLINIC_ID`, rồi `ctx.the_clinic_id()`). SQL mới dùng `ctx.the_clinic_id()`, không đọc `app.clinic_id`.
- **Cửa của agent (`clinic_agent`)**: chín view tối thiểu (`patient_ref`, `patient_appointment`, `patient_open_task`, `patient_care_plan`, `patient_last_session`, `consent_current`, `identity_verified`, `channel_policy`, `message_template_approved`; **không** SĐT, ngày sinh, địa chỉ, văn bản lâm sàng tự do, ảnh, thông tin đăng nhập) và các hàm `SECURITY DEFINER` có audit với tác nhân `agent` (`touch_identity`, `resolve_identity`, `create_review_item` idempotent theo `job_id`, cùng các hàm liên kết danh tính của `p0001`). `h2_0007` thêm hai hàm cùng loại: `clinic_agent.record_retention_run(scope, counts)` (cả hai role gọi được; ghi đúng một dòng tóm tắt `retention.run` vào `clinic.audit_log` với tác nhân `system`, `counts` chỉ là JSON phẳng các số nguyên không âm nên không mang được PII; đây là cách duy nhất để worker, vốn không có quyền ghi `clinic.*`, để lại dấu vết) và `clinic_agent.retention_purge_link_attempts(cutoff, limit, dry_run)` (chỉ `be_app`; `identity_link_attempt` là bằng chứng nên `p0001` đã thu hồi UPDATE và DELETE của mọi role, hàm này là ngoại lệ duy nhất cho việc xóa theo tuổi: từ chối mốc trẻ hơn một giờ vì bộ giới hạn tốc độ của luồng liên kết đếm lần sai trong giờ gần nhất, và chỉ chạm phòng khám của giao dịch hiện tại). View chạy bằng quyền chủ nên vẫn tự lọc theo mã cài đặt (`ctx.the_clinic_id()`, thêm một lớp phòng thủ) và khai báo `security_barrier`.
- **Ai xóa gì (tác vụ retention, mục 2)**:

| Scope | Tiến trình, role | Bảng / dữ liệu | Ngày (biến `PEMA_RETENTION_*`, 0 = giữ mãi) | Mặc định |
|---|---|---|---|---|
| `agent` | worker, `agent_worker` | `agent.history` (+ ảnh, mô tả, tóm tắt thread nhàn rỗi) | `HISTORY_DAYS` | 0 |
| `agent` | worker | `agent.memories` | `MEMORY_DAYS` | 0 |
| `agent` | worker | `agent.usage` (+ `usage_steps` theo cascade) | `USAGE_DAYS` | 0 |
| `agent` | worker | `agent.usage_steps` (trace thô) | `TRACE_DAYS`, bỏ trống = khóa chỉnh `AGENT_TRACE_RETENTION_DAYS` | 7 |
| `agent` | worker | file ảnh trên volume và `agent.image_descriptions` | `MEDIA_DAYS`, bỏ trống = `MEDIA_RETENTION_DAYS` | 7 |
| `agent` | worker | `agent.job_runs` đã xong | `JOB_RUN_DAYS` | 30 |
| `clinic` | api, `be_app` | `clinic.message` của hội thoại đóng, rồi hội thoại rỗng không có `review_item` | `MESSAGE_DAYS` | 0 |
| `clinic` | api | `clinic.auth_session` hết hạn | `AUTH_SESSION_DAYS` (sau hạn) | 1 |
| `clinic` | api | `clinic.identity_link_code` hết hạn hoặc đã dùng | `LINK_CODE_DAYS` | 7 |
| `clinic` | api | `clinic.identity_link_attempt` (qua `retention_purge_link_attempts`) | `LINK_ATTEMPT_DAYS` (tối thiểu 1 giờ) | 30 |

  Cả hai tiến trình còn nhận `PEMA_RETENTION_INTERVAL_SECONDS` và `PEMA_RETENTION_BATCH_SIZE`. `docker-compose.yml` liệt kê từng biến theo tên và đưa cho mỗi tiến trình đúng nhóm của scope nó (test `test_compose_passes_every_retention_setting_to_the_process_that_reads_it` khóa điều này). **Chưa có quy tắc xóa** cho `review_item` đã quyết, `display_name` và `contacts`, `crm_activity` và tóm tắt hội thoại (mục 13).
- **Quy tắc DB cho gói mới**: không sửa `0001..0003`; thêm migration riêng; bảng mới có `clinic_id` (khóa ngoại tới `clinic.clinic`) và grant đúng vai trò, **không RLS, không policy**; **không bao giờ** cấp bảng thô cho `agent_worker`.
- **Dữ liệu bệnh nhân không vào kho vector.** KB chỉ chứa tài liệu của phòng khám (hư cấu trong repo). Câu hỏi tra KB được nhúng cục bộ; máy khách nhúng từ chối địa chỉ công cộng trừ khi `PEMA_EMBEDDING_ALLOW_REMOTE=true`.
- Thời gian lưu trong DB là UTC có múi giờ; ranh giới API là `+07:00`; "ngày" của trần và usage tính theo `PEMA_BOT_TIMEZONE`.

## 4. Luồng tin nhắn

### 4.1 Chuẩn tắc (cả hai hồ sơ)

```
Zalo ─► webhook / polling
  C1: verify_webhook, parse_inbound, chống trùng update_id (agent.channel_update_seen), danh sách cho phép
      ghi agent.history (ngữ cảnh) và clinic.message (Inbox), gộp tin theo từng người (debounce 2500 ms)
  ─► TurnQueue.enqueue(TurnJob)                                             [tiến trình api, be_app]
Worker (agent_worker): giữ ThreadLock(account, thread) ─► AgentEngine.run_turn
   before_llm ──► vòng lặp (tool) ──► after_llm ──► on_outbound
  ─► SEND (staff_assistant)  hoặc  HOLD_FOR_REVIEW (patient_channel: tạo review_item)
  ─► ChannelPort.send_text theo phần                                        [tiến trình worker]
```

Tin đến giữa lúc lượt đang chạy được gộp vào lượt đó (không thành lượt riêng); hai lượt của một thread không bao giờ chồng nhau.

### 4.2 `patient_channel` từng bước

1. **Danh sách cho phép** và chống trùng. Tin vào cả hai kho (lịch sử và Inbox).
2. **`before_llm`** trên lô tin của một người:
   - quét **cờ đỏ** trên văn bản chuẩn hóa; có cờ thì tạo `triage_alert` (cần bác sĩ), thêm `media_flag` nếu có ảnh, trả `HAND_OFF`; **mô hình không được gọi**, không có tin nào được gửi;
   - ảnh hoặc tệp (không có chữ đỏ): `media_flag`, `HAND_OFF`;
   - chưa xác minh: thử liên kết từ nội dung tin (SĐT băm hoặc mã lễ tân), tạo `identity_check` khi cần; mô hình nhận câu hệ thống "hỏi cách xác minh";
   - **che PII** các tin còn lại, giữ phiên che trong bộ nhớ có hạn dùng (`MaskVault`).
3. **Vòng lặp tool** với văn bản đã che; tool bị lọc theo hồ sơ (`filter_tool_keys`); tool phòng khám đi qua `AgentFacingClinicActions` (cùng action với UI), bệnh nhân lấy từ danh tính đã xác minh của lượt.
4. **`after_llm`** khôi phục chỉ tên trong câu trả lời.
5. **`on_outbound` → `HOLD_FOR_REVIEW`**: người gọi tạo `reply_draft` (idempotent theo id tin), nháp nằm ở hàng chờ.
6. **Nhân viên duyệt** (sửa tuỳ ý) ở `/review`: văn bản đã duyệt được lưu `queued` cùng giao dịch với quyết định, rồi giao cho kênh qua `RegistryOutboundDelivery` (tài khoản đã nhận tin của bệnh nhân, tìm qua dòng `agent.threads` của hội thoại; hoạt động gần nhất nếu hai tài khoản cùng biết bệnh nhân; chỉ khi không dòng nào khớp mới rơi về tài khoản đang chạy đầu tiên theo id, kèm cảnh báo log). Kill switch, trần và cửa sổ giờ vẫn áp dụng nếu tin thuộc nguồn chủ động.

### 4.3 `staff_assistant`

Mọi hook trả như `PermissivePolicyHooks`: không cờ đỏ, không che PII, `on_outbound` = gửi thẳng, tool ảnh/web theo cấu hình. Đây là hành vi của zalo-agent gốc cho nhóm nhân viên nội bộ; không nhận tool phòng khám.

### 4.4 Thất bại và đóng

Policy không quyết được thì đóng (xem SPEC-AI01 mục 2). Lượt lỗi trả `AgentTurnError` có phân loại; lượt rơi ra ngoài `process_turn_job` được ghi log và không làm chết worker; lỗi Redis có lùi bước, không quay vòng bận.

## 5. Kênh Zalo

- **Bot API** (`ZaloBotChannel`): `polling` (mặc định) hoặc `webhook`; hai chế độ loại trừ nhau ở Zalo, runner gỡ webhook thừa trước khi poll. Bí mật webhook không lưu mà **dẫn xuất** (HMAC của `phòng khám|account` bằng `PEMA_SECRET_ENCRYPTION_KEY`, 64 ký tự hex), gửi lại kèm `setWebhook` mỗi lần account khởi động; so sánh thời gian hằng số. Chế độ webhook cần `PEMA_ZALO_BOT_WEBHOOK_BASE_URL` HTTPS công khai (Zalo từ chối địa chỉ nội bộ). Token bot nhập ở UI, mã hóa lưu.
- **Zalo cá nhân**: **không chính thức; rủi ro khóa hoặc cấm tài khoản và vi phạm điều khoản Zalo.** Dùng tài khoản phụ, không bao giờ tài khoản chính hay tài khoản gắn thanh toán. Các lớp an toàn (README cầu nối): cờ tắt mặc định; trần riêng mỗi account (`ZALO_BRIDGE_MAX_PROACTIVE_PER_DAY_PER_ACCOUNT` mặc định 100, `ZALO_BRIDGE_MAX_SENDS_PER_MINUTE_PER_ACCOUNT` mặc định 20); breaker sau 5 lần Zalo từ chối liên tiếp thì account vào `blocked`; thông tin đăng nhập **không ghi đĩa** (API giữ bản mã hóa AES-256-GCM ở `agent.accounts.credential_enc`, đưa vào bộ nhớ cầu nối khi `start`); mọi yêu cầu và sự kiện ký HMAC-SHA256 cửa sổ 5 phút; log không chứa văn bản, tên, SĐT, cookie. Khi cầu nối báo `blocked`, `logged_out` hay `session_dead`, API **bật kill switch**, bỏ kênh khỏi registry và ghi audit; kết nối lại **không** tự tắt kill switch. Dừng khẩn: UI, lệnh `pnpm kill-switch` trên máy cầu nối, `stop-all`, tắt cờ, giết tiến trình, hoặc đăng xuất thiết bị trên điện thoại.
- **OA/ZNS**: stub; cửa sổ tương tác 7 ngày và mẫu ZNS là luật của OA API, không áp dụng cho Bot API, chưa làm.
- Cả hai kênh qua cùng `ChannelPort`; khác biệt khả năng nằm ở `ChannelCapabilities` (ví dụ `blocked_tools` là dữ liệu).

## 6. Bộ lập lịch và luật CRM

```
CRM rules (be_app, tiến trình api): luật + bệnh nhân + sự kiện nguồn ─► crm_task (+ SchedulerPort.create_job, dedupe_key)
Scheduler worker (agent_worker): job đến hạn của phòng khám duy nhất:
   kind message (mẫu đã duyệt)  |  kind agent (lượt cô lập)
   ─► check_job ─► on_outbound ─► guard chủ động ─► ChannelPort.send_text
```

Guard chủ động theo thứ tự: account chạy ─► thread còn hiệu lực ─► kênh bật và **kill switch tắt** (`clinic_agent.channel_policy`, đọc lại mỗi lần) ─► cửa sổ giờ ─► trần ngày giữ chỗ **nguyên tử** (upsert có điều kiện; hoàn lại nếu gửi lỗi) ─► hàng đợi cách nhau `SCHEDULER_SEND_GAP_MS`. Khóa Redis thay cho giả định "một tiến trình đồng bộ" của bản gốc. Trần mặc định 10 mỗi ngày; khóa theo `patient:account` trong `patient_channel`. Khi cả hook lẫn `channel_setting.daily_cap` có giá trị, số nhỏ hơn thắng.

Luật CRM chạy ở API vì cần đọc rộng `clinic.*` (worker không đọc được). Runner có thể chạy tay (CLI) hoặc theo chu kỳ; chạy lại và chạy từ hai nơi đều an toàn (khóa việc, `dedupe_key`).

## 7. Tầng an toàn (tóm tắt, theo thứ tự trên đường đi của một tin)

1. Danh sách cho phép; chống trùng update.
2. **Cờ đỏ → bác sĩ trước LLM.**
3. Ảnh/tệp → người; agent không phân tích.
4. **Che PII** trước mô hình; khôi phục chỉ tên.
5. **Xác minh `zalo_uid`** trước khi nêu tên, lịch, thuốc; tool không nhận bệnh nhân làm tham số.
6. Chỉ trích KB đã được bác sĩ ký duyệt; tool ảnh/web/MCP/`save_memory` tắt.
7. **Mọi tin ra khách vào hàng duyệt**; mục lâm sàng chỉ bác sĩ/chủ duyệt.
8. Bộ lập lịch: mẫu đã duyệt, opt-out, sinh nhật không tự gửi, trần, kill switch, cửa sổ giờ.
9. Role tối thiểu và grant (không còn RLS: cách ly giữa phòng khám nằm ở hạ tầng, mục 8), audit không sửa được, bí mật mã hóa, log không PII.

Các tầng độc lập: bỏ lọt ở tầng này (ví dụ tên viết thường không được che) thì tầng sau (hàng duyệt) là lưới an toàn; SPEC-AI01 mục 2.3 nêu giới hạn từng tầng.

## 8. Bảo mật

- **Xác thực**: đăng nhập chỉ bằng email và mật khẩu (không còn mã phòng khám; email là khóa tra tài khoản trong CSDL của bản cài). Cookie HttpOnly sau đăng nhập (JWT; mật khẩu argon2 từng người). `PEMA_JWT_SECRET` bắt buộc. Phiên có hai đồng hồ: hạn trượt (`PEMA_SESSION_TTL_MINUTES`, 480 phút, `refresh` đẩy tới) và **hạn tuyệt đối** `absolute_expires_at` = lúc đăng nhập + `PEMA_SESSION_ABSOLUTE_DAYS` (mặc định 7, hợp lệ 1 đến 30, ngoài khoảng thì API từ chối khởi động), không `refresh` nào đẩy được. Chủ phòng khám đặt lại mật khẩu nhân viên bằng `POST /api/v1/admin/users/{user_id}/password` (quyền `admin.users`, chỉ chủ; mọi phiên của người đó bị thu hồi ngay; tối đa 5 lần mỗi phút mỗi chủ). **Tài khoản nhân viên** (vòng H4, `pema/api/dashboard_staff_store.py`, `routers/admin_users.py`): `GET /admin/users` cho chủ và quản lý (`admin.users.read`: danh sách cùng phòng khám, lọc vai trò, trạng thái, tìm theo tên hoặc email, phân trang, không bao giờ trả mật khẩu hay hash); `POST` (tạo, mật khẩu ban đầu do chủ nhập, 8 ký tự trở lên, 409 khi trùng email, 5 lần mỗi phút mỗi chủ) và `PATCH /admin/users/{user_id}` (đổi họ tên, vai trò, khóa hoặc mở khóa, có `version`) chỉ chủ (`admin.users`). Không xóa cứng: đường ra là khóa (`active = false`), tài khoản khóa không đăng nhập được. Khóa hoặc đổi vai trò thì thu hồi mọi phiên của người đó; chủ không tự khóa hay tự đổi vai trò của mình (422); phòng khám luôn còn ít nhất một chủ đang hoạt động (422, các chủ đang hoạt động bị khóa `FOR UPDATE` trước khi đếm nên hai chủ không thể cùng hạ nhau); người khác phòng khám hoặc vai trò `patient` là 404. Audit ghi tên trường, vai trò và id, không ghi họ tên, email hay mật khẩu.
- **Bề mặt cách ly (đổi từ RLS sang hạ tầng)**: trước `st_0009` một CSDL chứa được nhiều phòng khám và RLS (`clinic_id = ctx.current_clinic_id()`) là chốt cách ly, nhưng chính tiến trình tự đặt `app.clinic_id` nên một tiến trình bị chiếm vẫn đọc được phòng khám khác (SEC-12). Nay mỗi bản cài MỘT phòng khám: server, Postgres, Redis, tài khoản Zalo, `PEMA_JWT_SECRET` và `PEMA_SECRET_ENCRYPTION_KEY` riêng, nên không có đường rò giữa phòng khám qua phần mềm. `be_app` đọc mọi dòng của bảng nó có grant, và điều đó chấp nhận được vì chỉ có một phòng khám trong CSDL. Ranh giới còn lại bên trong một bản cài vẫn là grant: `agent_worker` không có gì trên `clinic.*` (chỉ view/hàm `clinic_agent`), `audit_log` chỉ chèn. Đổi lại, vì mọi dữ liệu của phòng khám nằm trong MỘT CSDL, các thứ canh cửa vào CSDL đó quan trọng hơn: mật khẩu và grant của hai role, `CONNECT` bị thu hồi khỏi PUBLIC, cổng Postgres/Redis bind loopback hoặc Tailscale, và nhất là bản sao lưu (một tệp là toàn bộ phòng khám). Xem SECURITY-REVIEW-AI01 mục 7.
- **Phân quyền**: deny by default; menu FE chỉ là tiện ích. Test `test_admin_access_matrix.py` kiểm 401/403/200 từng họ route admin.
- **Bí mật**: AES-256-GCM với `PEMA_SECRET_ENCRYPTION_KEY` (64 hex); DTO không mang bí mật; `infra/.env` chmod 600, ngoài git, `gen-secrets.sh` từ chối ghi đè.
- **Reverse proxy**: xem mục 10 (Caddy, `PEMA_TRUSTED_PROXIES`, cookie `Secure`). Địa chỉ client của giới hạn đăng nhập chỉ tin `X-Forwarded-For` khi kết nối TCP đến từ một proxy trong `PEMA_TRUSTED_PROXIES`.
- **Mạng**: mọi cổng publish bind loopback mặc định; muốn truy cập từ máy khác thì bind vào IP Tailscale, **không bao giờ 0.0.0.0** trên máy có IP công cộng (Docker publish vòng qua ufw nên địa chỉ bind mới là kiểm soát thật). Postgres, Redis, Ollama **không** ra internet; cầu nối chỉ nội bộ (`expose`, không `ports`).
- **SSRF và tải xuống**: chặn địa chỉ riêng, tải từ xa an toàn, trần zip/xml, worker trích có timeout (kế thừa từ gốc).
- **MCP**: mặc định chặn theo từng agent, dấu vân tay phát hiện thay đổi công cụ, `patient_channel` chặn mọi tool MCP.
- **Log**: ID và mã, không PII; logger che khóa nhạy cảm nhưng mã không dựa vào đó.
- Review bảo mật của gói G (PII, grant DB, token, SSRF) là việc của lượt tích hợp; kết quả của lượt đó nằm trong báo cáo của G, **không** được tài liệu này tái khẳng định.

## 9. Mô hình và tri thức

- **Trạng thái 2026-10-02:** agent gọi API LLM bên thứ ba qua cùng ba adapter (`openai-compatible`, `anthropic`, `google`), cấu hình trên màn Quản trị > Model hoặc `LLM_*` trong `infra/.env`. Ollama và embedding `bge-m3` **tạm tắt** (nhãn `TẠM TẮT LLM LOCAL` trong compose, Makefile, `.env.example`, preset FE; `PEMA_EMBEDDING_ENABLED` mặc định `false`), nên KB chỉ tìm từ khóa. Các ghi chú Ollama dưới đây mô tả cấu hình khi bật lại.
- LLM qua provider `openai-compatible` (Ollama hoặc llama-server); thêm adapter Anthropic và Gemini. Quyết định chốt: Qwen3-8B Q5_K_M và `bge-m3`. Luôn gọi bằng tên `pema-chat` (do `pull-models.sh` và dịch vụ `ollama-pull` tạo, có `num_ctx` 16384): gọi thẳng tên GGUF mà không đặt `num_ctx` thì Ollama nạp ngữ cảnh 40960, mô hình phình 13 GB và 18% chạy trên CPU (F đã đo).
- **Đã đo (F)**: Q5_K_M, `num_ctx 16384`, `OLLAMA_NUM_PARALLEL=2`, KV q8_0, Ollama trong Docker trên RTX 3060 12 GB (Windows, GPU dùng chung với màn hình): `pema-chat` 8,2 GB và `bge-m3` 664 MB, 100% GPU, tổng 9,5 GB. **Chưa đo**: Ubuntu không màn hình, Q6_K, chất lượng gọi tool và tiếng Việt của mô hình với engine này (cần chạy `evals`).
- KB: Postgres FTS (`ts_rank_cd` trên cột bỏ dấu) + pgvector hợp nhất bằng RRF; phần vector là mở rộng duy nhất so với bản gốc. `PEMA_EMBEDDING_ENABLED=false` thì chỉ tìm từ khóa.
- Kế toán token và ngân sách ngữ cảnh theo token được giữ từ bản gốc (`usage`, `usage_steps`, `trim_context_to_budget`).

## 10. Triển khai

Compose tại `infra/docker-compose.yml`, gọi từ `pema-agent/` (Makefile): mặc định dựng `postgres`, `redis`, `migrate` (một lần: role + `alembic upgrade heads`), `api`; profile `worker`, `frontend`, `proxy`, `bridge`, `ollama`, `app`. Một image Python cho `api`, `worker`, `migrate` (đa tầng, `uv sync --locked`, chạy không root uid 10001).

| Mô hình | Stack lõi | GPU | Khi nào |
|---|---|---|---|
| A. Một máy | PC Ubuntu có RTX 3060 | cùng máy | Bắt đầu, thử nghiệm |
| B. Server phòng khám + PC GPU | máy chủ nhỏ tại phòng khám | PC GPU qua LAN/Tailscale | Có máy chủ 24/7 |
| C. Cloud Việt Nam + PC GPU | VPS/cloud VN | PC GPU tại phòng khám qua Tailscale | Cần endpoint công khai, sao lưu ngoài phòng khám |

**Reverse proxy (Caddy, profile `proxy`).** Hai cách chạy không trộn: phát triển (không proxy: api và frontend publish loopback, không TLS, một máy) và sau Caddy (máy chủ phòng khám hoặc máy người khác truy cập: chỉ Caddy publish 80/443). Lệnh: `make up-proxy` (= `docker compose -f infra/docker-compose.yml -f infra/docker-compose.proxy.yml --env-file infra/.env --profile proxy --profile worker up -d --build`); `docker-compose.proxy.yml` dùng `!reset` (Compose 2.24+) xóa `ports` của api và frontend, để chúng chỉ `expose` trong mạng compose. Caddy chỉ nối mạng `edge` (subnet cố định `PEMA_PROXY_SUBNET`, Caddy ở `PEMA_PROXY_IP`, mặc định `172.29.80.2`; Docker chỉ cấp địa chỉ cho api và frontend từ `PEMA_PROXY_IP_RANGE`, nửa trên, nên không tranh địa chỉ của Caddy) nên không với tới Postgres, Redis, cầu nối. Định tuyến: `/api/v1/*` và `/healthz` về `api:8000` (webhook cầu nối `/api/v1/webhooks/zalo-bridge/*` trả 404 từ bên ngoài), còn lại về `frontend:3000`. Ba chế độ TLS chọn bằng `PEMA_PROXY_TLS` kèm địa chỉ `PEMA_PUBLIC_DOMAIN`: `auto` (tên miền thật trỏ về máy; Let's Encrypt; cần 80 và 443 mở ra internet và `PEMA_PROXY_BIND=0.0.0.0` hoặc IP công cộng; có HSTS 1 năm), `internal` (chưa có tên miền; CA nội bộ của Caddy ký, trình duyệt cảnh báo tới khi cài gốc CA; không HSTS), `off` (HTTP thuần, **chỉ** qua Tailscale/WireGuard, kèm `PEMA_SESSION_COOKIE_SECURE=false` và `PEMA_PROXY_BIND` là IP Tailscale). Caddy ghi đè `X-Forwarded-For` bằng địa chỉ nó thấy; API chỉ tin header đó khi ngang hàng TCP nằm trong `PEMA_TRUSTED_PROXIES` (mặc định = `PEMA_PROXY_IP`; danh sách rỗng là không tin ai), lấy phần tử đầu tiên từ phải sang không phải proxy tin cậy (`client_ip.py`), nên client không giả được khóa giới hạn đăng nhập; `PEMA_DASHBOARD_BEHIND_PROXY=true` là công tắc. Cookie phiên `HttpOnly`, `SameSite=Lax`, `Secure` (`PEMA_SESSION_COOKIE_SECURE=true`, chỉ đặt false cho chế độ `off`). FE đọc địa chỉ API lúc chạy từ `PEMA_API_INTERNAL_URL` (route handler, không build arg): đổi giá trị rồi `up -d frontend`, không dựng lại ảnh. Caddy cắt thân yêu cầu quá 4 MiB bằng 413 (riêng hai route tải KB được 105 MiB), `read_header` 10 giây, nén zstd và gzip, log truy cập JSON không chứa query string, `Cookie`, `Authorization`, `Set-Cookie`. Chi tiết và cách cài gốc CA ở [`infra/README.md`](../infra/README.md) mục Reverse proxy.

**Một bản cài, một phòng khám.** Compose dựng đúng một phòng khám: `PEMA_CLINIC_NAME` và `PEMA_CLINIC_ID` (tùy chọn) được truyền cho `migrate`, `api`, `worker`; `migrate.sh` kiểm `clinic.clinic` đúng một dòng sau khi nâng cấp và in tên. Phòng khám thứ hai là **một bộ mới hoàn toàn**: `infra/.env` khác (mật khẩu, `PEMA_JWT_SECRET`, `PEMA_SECRET_ENCRYPTION_KEY` khác), `COMPOSE_PROJECT_NAME` khác hoặc tốt nhất là máy chủ khác, Postgres và Redis riêng, cổng/subnet/tên miền riêng, tài khoản Zalo riêng, thư mục sao lưu và khóa age riêng; không bao giờ thêm dòng thứ hai vào cùng CSDL. Chi tiết: `infra/README.md` mục "One system, one clinic". Webhook Zalo Bot nay là `/api/v1/webhooks/zalo-bot/<account_id>` (không có đoạn phòng khám).

Hướng dẫn chi tiết (Ubuntu 24.04, driver NVIDIA, Docker, Ollama, Tailscale, ufw, sao lưu, UPS, danh sách bàn giao) ở [`infra/ubuntu/HUONG-DAN-UBUNTU.md`](../infra/ubuntu/HUONG-DAN-UBUNTU.md); tổng quan hạ tầng ở [`infra/README.md`](../infra/README.md).

Sao lưu: `pg_dump -Fc` + `pg_dumpall --globals-only`, kiểm bằng `pg_restore --list`, mã hóa age/gpg, giữ 14 ngày (mặc định), có hook chép ra ngoài; khôi phục không bao giờ ghi đè DB đang chạy. Điểm mất dữ liệu tối đa một ngày. **Đường mã hóa age/gpg chưa chạy thử** (chỉ nhánh không mã hóa đã chạy); WAL liên tục và UPS chưa làm.

## 11. Quan hệ phái sinh và giấy phép

Phần engine là **bản dịch từng module** của `vuhai2002/zalo-agent` 0.3.1, commit `bf154de68335e73073c2b6913c731be22ca3d0e6` (MIT, © 2026 Vu Van Hai), kèm `zca-js` 2.1.2 (MIT) trong cầu nối Node. Giữ tên khái niệm, hằng số, ngưỡng và lý do trong chú thích gốc; mỗi file dịch bắt đầu bằng `# ported from: src/<đường dẫn>.ts` và ghi chỗ lệch bắt buộc ở docstring (SQLite → Postgres, Vercel AI SDK → `openai`, đồng bộ → async, một tiến trình → Redis). Thêm: CRM phòng khám, hồ sơ chính sách, pgvector, cầu nối cho `zca-js`, FE Next.js thay cho SPA Vite. Thông báo bản quyền nguyên văn ở [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md); repo không thêm hạn chế nào ngoài MIT. Bản tham chiếu nằm ngoài repo (`E:\Desktop\zalo-agent-ref`, đọc-chỉ); cách tạo lại và bảng ánh xạ ở PORT-MAP.

Mã CRM không phải dẫn xuất từ zalo-agent: nó dịch `prototype/shared/crm-data.js` và `crm-automation.js` của chính repo này, có test tương đương.

## 12. Điều đã chốt và điều chưa kiểm chứng

Quyết định đã chốt: SCOPE-AI01 mục 7. Điều chưa kiểm chứng (Zalo thật, LLM thật, Ollama, Ubuntu thật, sao lưu mã hóa, thiết bị thật cho FE, hiệu năng): SCOPE-AI01 mục 8. Hai thông điệp quan trọng nhất, nhắc lại ở đây vì chúng quyết định cách đọc mọi tài liệu khác:

- Các test chạy với **đồ giả**; phần DB, role/grant và vòng khép kín cần Postgres + Redis tạm và mới chứng minh được khi chạy với chúng.
- Chưa có tin Zalo thật nào, lời gọi mô hình thật nào, hay máy Ubuntu thật nào đi qua hệ thống này.

## 13. Quyết định kiến trúc còn mở

Việc cần chủ phòng khám hoặc bác sĩ quyết định (cờ đỏ, phân quyền, persona xác minh, trấn an tự động, nhắc trước khi duyệt mẫu, trần 10, thời hạn lưu theo NĐ 13/2023, vị trí server, lưu tệp, webhook HTTPS, MCP cho bệnh nhân): SCOPE-AI01 mục 9. Phần kỹ thuật còn mở:

- **Chọn account khi nhiều account cùng loại kênh trong một phòng khám**: đã sửa ở vòng cuối (`pema/composition/outbound.py`): chọn account có dòng `agent.threads` cho thread của hội thoại. Còn lại: `clinic.conversation` vẫn không có cột account (chưa đổi schema); hội thoại do nhân viên tạo tay, chưa có tin đến, rơi về account đầu tiên theo id.
- ~~Một worker mỗi phòng khám hay chung~~: đã đóng bởi single-tenant (một bản cài, một phòng khám, một worker). Còn lại: tiến trình nào sở hữu account Zalo nào trong một phòng khám có nhiều account.
- **Liên kết phiên bệnh nhân với `clinic.patient`** (vai trò `patient` rỗng); cần cho ứng dụng bệnh nhân gọi API này.
- **Đặt lịch của agent**: hiện là đề xuất; cần chủ phòng khám xác nhận quy trình.
- **Lưu tệp**: volume cục bộ hay object storage (cũng là việc mở ở SCOPE).
- **Khôi phục sao lưu và WAL liên tục**; UPS.
- **Migration**: gói mới thêm migration riêng và có nhiều đầu; `g_0005_merge_heads` rồi `h_0008_merge_heads` (gộp `b1_0007` và `h2_0007`) đã gộp; gói sau phải gộp tiếp và giữ `alembic heads` ở MỘT đầu (test `test_the_migration_chain_has_one_head`); trên `feat/single-tenant` đầu duy nhất là `st_0009_single_tenant`.
- **Đã xử lý ở vòng sửa cuối**: ảnh Docker của cầu nối (bỏ bước build; chạy bằng tsx, `tsx` chuyển sang `dependencies`; compose đặt `PEMA_ZALO_BRIDGE_HOST=0.0.0.0` trong container, `PEMA_ZALO_PERSONAL_ENABLED`, `PEMA_API_BASE_URL`, healthcheck, vẫn chỉ `expose`) và của FE đã dựng và chạy thử thật (địa chỉ API của FE sau đó đổi từ build arg sang đọc lúc chạy, xem mục dưới); ghi chú "chờ gói G/E/C2" đã bỏ; eval đã nằm trong `make test` qua `testpaths` (`../evals`); tool `review_item.create` đã đăng ký; `POST /auth/password` đã có.
- **Đã xử lý ở vòng tích hợp H** (năm việc từng nằm trong danh sách mở): (1) hạn tuyệt đối của phiên (`PEMA_SESSION_ABSOLUTE_DAYS`, migration `b1_0007`); (2) route chủ đặt lại mật khẩu nhân viên (`POST /api/v1/admin/users/{user_id}/password`, quyền `admin.users`); (3) tác vụ xóa theo thời hạn lưu (`pema.retention`, CLI `python -m pema.workers.retention`, migration `h2_0007`); (4) reverse proxy (Caddy, profile `proxy`, `PEMA_TRUSTED_PROXIES`, cookie `Secure`); (5) địa chỉ API của FE đọc lúc chạy (`PEMA_API_INTERNAL_URL`, route handler thay `rewrites()` lúc build). Đã dựng stack thật `postgres redis migrate api frontend caddy` ở chế độ `internal`, đăng nhập thật qua Caddy bằng curl, và chạy `retention --dry-run` trong container (số liệu ở báo cáo của vòng).
- **Còn mở sau vòng H** (việc thật, chưa làm):
  - Thời hạn lưu cụ thể từng nhóm dữ liệu là quyết định của chủ phòng khám; mặc định của mã chỉ để chạy được (SCOPE-AI01 mục 9, việc 7).
  - `review_item` đã quyết, `display_name` và `contacts`, `crm_activity`, tóm tắt hội thoại **chưa có quy tắc xóa**: tác vụ retention không động tới chúng.
  - Ô "Phụ trách" của Việc hôm nay vẫn chỉ có "Tôi" và "Giữ nguyên": dùng danh sách nhân viên cho ô đó cần quyền đọc danh sách cho `cs_staff` và `reception` (hiện chỉ chủ và quản lý có `admin.users.read`); mở quyền đó là quyết định của chủ phòng khám, chưa mở.
  - Chưa quyết (chủ phòng khám): owner có được khóa, đổi vai trò hay đặt lại mật khẩu của owner khác không. Hiện được phép, trừ chính mình và trừ việc làm mất chủ đang hoạt động cuối cùng.
  - Chưa thử Let's Encrypt thật (chế độ `auto`) và chưa đăng nhập thật qua proxy trên máy chủ công khai; chỉ chạy được chế độ `internal` trên máy dev.

## 14. Hai nhánh song song: đa phòng khám và một phòng khám

Hai nhánh cùng tồn tại; **tính năng về sau làm trên `feat/single-tenant` trước**.

| | `feat/ai-agent-backend` (đa phòng khám) | `feat/single-tenant` (một phòng khám mỗi bản cài) |
|---|---|---|
| Mô hình | một CSDL chứa nhiều phòng khám; mỗi bảng có `clinic_id` chọn phòng khám | một bản cài = MỘT phòng khám, có server, Postgres, Redis, Zalo, khóa mã hóa riêng |
| Cách ly | RLS (`clinic_isolation`, `ctx.current_clinic_id()`, `app.clinic_id` đặt theo giao dịch) | hạ tầng riêng cho từng phòng khám; không RLS; `be_app` đọc mọi dòng của một CSDL chỉ có một phòng khám |
| Hàm chọn phòng khám | `ctx.current_clinic_id`, `ctx.resolve_clinic(slug)`, `ctx.list_active_clinic_ids` | đã xóa; `ctx.the_clinic_id()` (báo lỗi khi chưa có phòng khám) |
| `clinic.clinic` | nhiều dòng, slug chọn phòng khám | đúng một dòng (`singleton`, `CHECK`, `UNIQUE`, trigger chặn xóa), slug cố định `clinic`, tạo bởi migration từ `PEMA_CLINIC_NAME` / `PEMA_CLINIC_ID` |
| Cột `clinic_id` | khóa chọn phòng khám | giữ nguyên làm mã cài đặt cố định (khóa ngoại, khóa kép vẫn chạy) |
| Đăng nhập | phòng khám (slug) + email + mật khẩu | email + mật khẩu |
| Webhook Zalo | `/api/v1/webhooks/zalo-bot/{clinic}/{account}` và `.../zalo-bridge/{clinic}/{account}` | `/api/v1/webhooks/zalo-bot/{account}` và `.../zalo-bridge/{account}` |
| Vòng nền | lặp qua `list_active_clinic_ids` | một lượt cho phòng khám duy nhất |
| Nhiều tài khoản Zalo | có | có (vẫn nhiều account trong một phòng khám) |
| Role `be_app`, `agent_worker`, view `clinic_agent`, audit, consent, che PII | có | giữ nguyên |
| Migration | đầu `h_0008_merge_heads` | thêm `st_0009_single_tenant` (đầu duy nhất; downgrade khôi phục policy và hàm cũ, dòng phòng khám còn lại) |
| Phòng khám thứ hai | thêm một dòng `clinic.clinic` | dựng một bộ mới hoàn toàn (`infra/README.md`) |

Lý do chọn một phòng khám mỗi bản cài: yêu cầu bảo mật cao của phòng khám, bệnh viện, ngân hàng (dữ liệu hai tổ chức không chung CSDL, Redis, khóa hay tiến trình; không phải tin vào một chốt phần mềm duy nhất). Cách làm tính năng: viết trên `feat/single-tenant`; nhánh đa phòng khám nhận bản backport chỉ khi có yêu cầu cụ thể, và hai nhánh không được gộp lại với nhau (migration `st_0009` bỏ RLS). Việc mở: ứng dụng bệnh nhân (web/KMP) và mọi client khác gọi đăng nhập theo slug hoặc đường webhook có đoạn phòng khám phải đổi theo (mục SCOPE-AI01 mục 9, việc 12).


## 15. Cập nhật trực tiếp và hiện diện (gói ST-R)

Worker (nháp, trả lời của agent) và API (webhook, thao tác của nhân viên) là hai tiến trình, nên một thay đổi ở tiến trình này phải tới luồng SSE do tiến trình kia phục vụ. Hai bên gặp nhau ở Redis pub/sub, MỘT kênh cho mỗi bản cài (`pema:live:<clinic_id>`):

```
nơi ghi (API hoặc worker) --commit--> emit_live(type, id) --gộp 200 ms--> PUBLISH --> Redis
                                                                                      |
 trình duyệt <-- GET /api/v1/events (SSE) <-- LiveHub (MỘT subscribe mỗi tiến trình API) <--+
```

* Cổng `LiveEventBus` (adapter Redis và adapter bộ nhớ cho test) nằm ở package `pema.live`, không import `pema.clinic`. Mã nghiệp vụ chỉ gọi `emit_live(...)` SAU khi commit; hàm không bao giờ ném lỗi, nên Redis hỏng không làm hỏng thao tác nghiệp vụ (chỉ ghi log không PII, tối đa mỗi 30 giây một dòng).
* Điểm phát: tin đến (`record_inbound_message`), nháp và cảnh báo (`create_review_item`), tin đi (`record_outbound_message`, `deliver_queued_message`), giao việc hoặc đổi trạng thái hội thoại, quyết định hàng đợi duyệt, giải quyết việc CSKH, lượt chạy luật CRM.
* Sự kiện chỉ nói "có gì đó đổi, hãy tải lại": `type` + `id`. FE tải lại bằng API thường nên phân quyền vẫn do backend quyết. Mỗi vai chỉ nhận loại sự kiện mà vai đó được đọc; luồng của bác sĩ (chỉ thấy bệnh nhân của mình) không mang id.
* Hiện diện: Redis, một sorted set mỗi hội thoại (điểm = thời điểm hết hạn), TTL 30 giây, nhịp 15 giây từ FE. Danh sách `viewers` đọc một lượt pipeline cho cả trang hội thoại. Redis hỏng thì `viewers` rỗng và nhịp vẫn trả 204. Không bao giờ chặn gửi.
* Hạ tầng: Caddy không nén `/api/v1/events` (`encode` có matcher loại trừ), `flush_interval -1` đã có ở `to_api`, header `Cache-Control: no-cache, no-transform` và `X-Accel-Buffering: no`.
* Giới hạn: 5 luồng mỗi người, 200 mỗi tiến trình API (đếm theo tiến trình; chạy nhiều tiến trình API thì cộng lại).
