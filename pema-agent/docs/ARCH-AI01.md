# Pema Agent — Architecture AI01

Đọc sau [MODULEMAP-AI01](MODULEMAP-AI01.md). Mô tả kiến trúc **đang có trong mã** (nhánh `feat/ai-agent-backend`, commit `1ce6cca`, 2026-10-02) và đích triển khai đã chọn. Phần chưa kiểm chứng được gắn nhãn thẳng; tổng hợp ở SCOPE-AI01 mục 8. Kiến trúc pilot của phòng khám nói chung (đa dịch vụ, tài chính) vẫn là [ARCH-PB01](../../docs/ARCH-PB01.md); tài liệu này chỉ là phần CSKH-agent và CRM phía server của nó, và **không thay thế** prototype web/KMP.

## 1. Cái nhìn container

```
 Bệnh nhân (Zalo)                                          Nhân viên (trình duyệt, qua Tailscale)
   │                                                            │
   ├─ Bot API ── polling ──────────────┐                        ▼
   │            └ webhook (HTTPS) ──┐  │                  Next.js (frontend, :3000)
   │                                │  │                        │  /api/* và /healthz được rewrite
   └─ Zalo cá nhân ─► Cầu nối Node ─┤  │                        ▼          (cookie phiên cùng origin)
        (zca-js, tuỳ chọn, cờ tắt)  │  │          ┌─────────────────────────────────┐
        HMAC, chỉ loopback/nội bộ   ▼  │          │ api (FastAPI, uvicorn 1 worker) │  role DB: be_app
                              /webhooks/*────────►│ webhook · routers mỏng · gộp tin │
                                       │          │ (batcher) · vòng luật CRM · auth │
                                       │          └──────┬──────────────────┬───────┘
                                       │      TurnQueue (Redis)            │ SQL (RLS)
                                       ▼                 ▼                 ▼
                                 ┌──────────────────────────┐   ┌─────────────────────────────┐
                                 │ worker (python -m        │   │ PostgreSQL 17 + pgvector    │
                                 │  pema.workers.main)      │   │  clinic.*  (CRM, RLS)       │
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
| `api` | `be_app` | Nhận webhook Zalo, phục vụ route nhân viên, gộp tin (debounce) rồi đưa `TurnJob` vào Redis, chạy vòng luật CRM mỗi `PEMA_CRM_RUNNER_INTERVAL_SECONDS`, duyệt và gửi tin đã duyệt | `uvicorn --factory pema.bootstrap:create_app --workers 1` (PLAN: 1 nhân CPU). Bộ gộp tin khôi phục các lô đang chờ khi khởi động |
| `worker` | `agent_worker` | Chạy lượt agent (`TurnWorker`, 4 lượt đồng thời mặc định, khoá theo thread), bộ lập lịch, nạp KB, nghe polling của account bot, các account cá nhân và quét tự chấp nhận kết bạn khi cờ bật, MCP manager, dọn ảnh/trace, trả lại lượt của worker chết | Không có đặc quyền nào trên `clinic.*`; hook chính sách chạy **trong** tiến trình này |
| `zalo-personal-bridge` (Node 22, tuỳ chọn) | không dùng DB | Bọc `zca-js`: đăng nhập QR, nghe sự kiện, gửi tin; giữ thông tin đăng nhập chỉ trong bộ nhớ | Profile compose `bridge`; mặc định tắt (`PEMA_ZALO_PERSONAL_ENABLED=false` trong mã) |
| `frontend` (Next.js, `output: "standalone"`) | không dùng DB | UI; chỉ nói với origin của chính nó, `next.config.ts` rewrite sang API | Profile compose `frontend` |
| `postgres` (pgvector pg17) | | `clinic`, `clinic_agent`, `agent`, `ctx` | scram, data checksums; cổng bind loopback mặc định |
| `redis` 7 | | Hàng đợi lượt (at-least-once, thời hạn nhìn thấy 20 phút), khoá thread, lô tin đang chờ, khoá bộ lập lịch, khoảng cách gửi theo account | mật khẩu, AOF, `noeviction` (hàng đợi và khoá không được bị đẩy ra) |
| Ollama / llama-server | | Chat và nhúng | Có thể là container (profile `ollama`) hoặc cài trực tiếp; **chỉ liên lạc qua HTTP** nên worker đặt cạnh DB và trỏ `LLM_BASE_URL` sang máy GPU |

Lý do tách `api` và `worker`: lượt agent có thể kéo dài nhiều phút (`LLM_TURN_TIMEOUT_MS` mặc định 900000), không được chặn webhook; worker chạy được trên máy GPU hoặc máy chủ; và nó **không cần** và **không có** quyền đọc bảng thô của phòng khám. Mỗi tiến trình chỉ nhận đúng một URL DB của vai trò mình (`PEMA_DATABASE_URL` cho api, `PEMA_WORKER_DATABASE_URL` cho worker); worker không giữ mật khẩu `be_app`.

Một account bot chỉ được **một** tiến trình nghe: chế độ `webhook` thì API nghe, chế độ `polling` thì worker nghe; tiến trình kia giữ đối tượng kênh chỉ để gửi. Tài khoản cá nhân vào bằng webhook có chữ ký HMAC từ cầu nối tới `/api/v1/webhooks/zalo-bridge/{clinic}/{account}`.

Nhiều phòng khám: mọi bảng có `clinic_id`; `ctx.list_active_clinic_ids()` cho các vòng nền lặp qua từng phòng khám. Chưa quyết một worker cho mỗi phòng khám hay worker chung.

## 3. Cơ sở dữ liệu

- **Schema**: `ctx` (hàm ngữ cảnh), `clinic` (CRM), `clinic_agent` (cửa của agent), `agent` (engine). Migration Alembic: `0001` clinic, `0002` agent (ghi cách ánh xạ mọi bảng SQLite gốc), `0003` clinic_agent; bổ sung `b1_0004`, `b2_0001`, `s_0004`, `p0001`; `g_0005` gộp đầu nhánh; chạy `alembic upgrade heads`.
- **`clinic.*`** (21 bảng): `clinic`, `user_account`, `auth_session`, `patient`, `episode`, `treatment_plan`, `treatment_session`, `appointment`, `consent`, `conversation`, `message`, `review_item`, `message_template`, `crm_rule`, `crm_task`, `crm_activity`, `channel_setting`, `channel_identity`, `identity_link_code`, `identity_link_attempt`, `audit_log`.
- **`agent.*`**: `accounts`, `agents`, `contacts`, `friend_requests`, `threads`, `history`, `memories`, `image_descriptions`, `usage`, `usage_steps`, `jobs`, `job_runs`, `proactive_send_counters`, `kb_document`, `kb_chunk` (vector 1024, `tsvector` trên cột đã bỏ dấu), `agent_kb_document`, `mcp_servers`, `agent_mcp_servers`, `runtime_settings`, `channel_update_seen`.
- **Hai kho, hai mục đích**: `agent.history` là kho ngữ cảnh cho LLM; `clinic.message` là Inbox chính thức nhân viên đọc. Tầng kênh ghi cả hai. `review_item` ở `clinic.review_item`.
- **Role**: `be_app` (DML trên `clinic.*` và `agent.*`; `audit_log` chỉ chèn và đọc: không sửa, không xóa) và `agent_worker` (DML trên `agent.*`; đọc view `clinic_agent`; EXECUTE hàm `clinic_agent`; **không có gì trên `clinic.*`**). Cả hai không sở hữu bảng nên RLS áp dụng. `bootstrap-roles.sh` tạo role NOLOGIN, đặt mật khẩu từ môi trường (psql đọc bằng `\getenv`, không qua argv; `log_statement` tắt cho phiên đó), và mặc định thu hồi `CONNECT` của PUBLIC. Mật khẩu rỗng thì role vẫn NOLOGIN.
- **RLS**: mọi bảng có `clinic_id` và `USING (clinic_id = ctx.current_clinic_id())`. Mở đơn vị công việc bằng `async with db.session(clinic_id) as s:` đặt `app.clinic_id` cho giao dịch; không có ngữ cảnh thì không có hàng.
- **Cửa của agent (`clinic_agent`)**: chín view tối thiểu (`patient_ref`, `patient_appointment`, `patient_open_task`, `patient_care_plan`, `patient_last_session`, `consent_current`, `identity_verified`, `channel_policy`, `message_template_approved`; **không** SĐT, ngày sinh, địa chỉ, văn bản lâm sàng tự do, ảnh, thông tin đăng nhập) và các hàm `SECURITY DEFINER` có audit với tác nhân `agent` (`touch_identity`, `resolve_identity`, `create_review_item` idempotent theo `job_id`, cùng các hàm liên kết danh tính của `p0001`). View chạy bằng quyền chủ nên tự lọc theo phòng khám và khai báo `security_barrier`.
- **Quy tắc DB cho gói mới**: không sửa `0001..0003`; thêm migration riêng; bảng mới có `clinic_id`, RLS, grant đúng vai trò; **không bao giờ** cấp bảng thô cho `agent_worker`.
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
6. **Nhân viên duyệt** (sửa tuỳ ý) ở `/review`: văn bản đã duyệt được lưu `queued` cùng giao dịch với quyết định, rồi giao cho kênh qua `RegistryOutboundDelivery` (tài khoản đầu tiên theo id đang chạy của loại kênh, trong phòng khám). Kill switch, trần và cửa sổ giờ vẫn áp dụng nếu tin thuộc nguồn chủ động.

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
Scheduler worker (agent_worker): mỗi phòng khám còn hoạt động, job đến hạn:
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
9. RLS, role tối thiểu, audit không sửa được, bí mật mã hóa, log không PII.

Các tầng độc lập: bỏ lọt ở tầng này (ví dụ tên viết thường không được che) thì tầng sau (hàng duyệt) là lưới an toàn; SPEC-AI01 mục 2.3 nêu giới hạn từng tầng.

## 8. Bảo mật

- **Xác thực**: cookie HttpOnly sau đăng nhập (JWT; mật khẩu argon2 từng người). `PEMA_JWT_SECRET` bắt buộc.
- **Phân quyền**: deny by default; menu FE chỉ là tiện ích. Test `test_admin_access_matrix.py` kiểm 401/403/200 từng họ route admin.
- **Bí mật**: AES-256-GCM với `PEMA_SECRET_ENCRYPTION_KEY` (64 hex); DTO không mang bí mật; `infra/.env` chmod 600, ngoài git, `gen-secrets.sh` từ chối ghi đè.
- **Mạng**: mọi cổng publish bind loopback mặc định; muốn truy cập từ máy khác thì bind vào IP Tailscale, **không bao giờ 0.0.0.0** trên máy có IP công cộng (Docker publish vòng qua ufw nên địa chỉ bind mới là kiểm soát thật). Postgres, Redis, Ollama **không** ra internet; cầu nối chỉ nội bộ (`expose`, không `ports`).
- **SSRF và tải xuống**: chặn địa chỉ riêng, tải từ xa an toàn, trần zip/xml, worker trích có timeout (kế thừa từ gốc).
- **MCP**: mặc định chặn theo từng agent, dấu vân tay phát hiện thay đổi công cụ, `patient_channel` chặn mọi tool MCP.
- **Log**: ID và mã, không PII; logger che khóa nhạy cảm nhưng mã không dựa vào đó.
- Review bảo mật của gói G (PII, grant DB, token, SSRF) là việc của lượt tích hợp; kết quả của lượt đó nằm trong báo cáo của G, **không** được tài liệu này tái khẳng định.

## 9. Mô hình và tri thức

- LLM qua provider `openai-compatible` (Ollama hoặc llama-server); thêm adapter Anthropic và Gemini. Quyết định chốt: Qwen3-8B Q5_K_M và `bge-m3`. Luôn gọi bằng tên `pema-chat` (do `pull-models.sh` và dịch vụ `ollama-pull` tạo, có `num_ctx` 16384): gọi thẳng tên GGUF mà không đặt `num_ctx` thì Ollama nạp ngữ cảnh 40960, mô hình phình 13 GB và 18% chạy trên CPU (F đã đo).
- **Đã đo (F)**: Q5_K_M, `num_ctx 16384`, `OLLAMA_NUM_PARALLEL=2`, KV q8_0, Ollama trong Docker trên RTX 3060 12 GB (Windows, GPU dùng chung với màn hình): `pema-chat` 8,2 GB và `bge-m3` 664 MB, 100% GPU, tổng 9,5 GB. **Chưa đo**: Ubuntu không màn hình, Q6_K, chất lượng gọi tool và tiếng Việt của mô hình với engine này (cần chạy `evals`).
- KB: Postgres FTS (`ts_rank_cd` trên cột bỏ dấu) + pgvector hợp nhất bằng RRF; phần vector là mở rộng duy nhất so với bản gốc. `PEMA_EMBEDDING_ENABLED=false` thì chỉ tìm từ khóa.
- Kế toán token và ngân sách ngữ cảnh theo token được giữ từ bản gốc (`usage`, `usage_steps`, `trim_context_to_budget`).

## 10. Triển khai

Compose tại `infra/docker-compose.yml`, gọi từ `pema-agent/` (Makefile): mặc định dựng `postgres`, `redis`, `migrate` (một lần: role + `alembic upgrade heads`), `api`; profile `worker`, `frontend`, `bridge`, `ollama`, `app`. Một image Python cho `api`, `worker`, `migrate` (đa tầng, `uv sync --locked`, chạy không root uid 10001).

| Mô hình | Stack lõi | GPU | Khi nào |
|---|---|---|---|
| A. Một máy | PC Ubuntu có RTX 3060 | cùng máy | Bắt đầu, thử nghiệm |
| B. Server phòng khám + PC GPU | máy chủ nhỏ tại phòng khám | PC GPU qua LAN/Tailscale | Có máy chủ 24/7 |
| C. Cloud Việt Nam + PC GPU | VPS/cloud VN | PC GPU tại phòng khám qua Tailscale | Cần endpoint công khai, sao lưu ngoài phòng khám |

Hướng dẫn chi tiết (Ubuntu 24.04, driver NVIDIA, Docker, Ollama, Tailscale, ufw, sao lưu, UPS, danh sách bàn giao) ở [`infra/ubuntu/HUONG-DAN-UBUNTU.md`](../infra/ubuntu/HUONG-DAN-UBUNTU.md); tổng quan hạ tầng ở [`infra/README.md`](../infra/README.md).

Sao lưu: `pg_dump -Fc` + `pg_dumpall --globals-only`, kiểm bằng `pg_restore --list`, mã hóa age/gpg, giữ 14 ngày (mặc định), có hook chép ra ngoài; khôi phục không bao giờ ghi đè DB đang chạy. Điểm mất dữ liệu tối đa một ngày. **Đường mã hóa age/gpg chưa chạy thử** (chỉ nhánh không mã hóa đã chạy); WAL liên tục và UPS chưa làm.

## 11. Quan hệ phái sinh và giấy phép

Phần engine là **bản dịch từng module** của `vuhai2002/zalo-agent` 0.3.1, commit `bf154de68335e73073c2b6913c731be22ca3d0e6` (MIT, © 2026 Vu Van Hai), kèm `zca-js` 2.1.2 (MIT) trong cầu nối Node. Giữ tên khái niệm, hằng số, ngưỡng và lý do trong chú thích gốc; mỗi file dịch bắt đầu bằng `# ported from: src/<đường dẫn>.ts` và ghi chỗ lệch bắt buộc ở docstring (SQLite → Postgres, Vercel AI SDK → `openai`, đồng bộ → async, một tiến trình → Redis). Thêm: CRM phòng khám, hồ sơ chính sách, pgvector, cầu nối cho `zca-js`, FE Next.js thay cho SPA Vite. Thông báo bản quyền nguyên văn ở [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md); repo không thêm hạn chế nào ngoài MIT. Bản tham chiếu nằm ngoài repo (`E:\Desktop\zalo-agent-ref`, đọc-chỉ); cách tạo lại và bảng ánh xạ ở PORT-MAP.

Mã CRM không phải dẫn xuất từ zalo-agent: nó dịch `prototype/shared/crm-data.js` và `crm-automation.js` của chính repo này, có test tương đương.

## 12. Điều đã chốt và điều chưa kiểm chứng

Quyết định đã chốt: SCOPE-AI01 mục 7. Điều chưa kiểm chứng (Zalo thật, LLM thật, Ollama, Ubuntu thật, sao lưu mã hóa, thiết bị thật cho FE, hiệu năng): SCOPE-AI01 mục 8. Hai thông điệp quan trọng nhất, nhắc lại ở đây vì chúng quyết định cách đọc mọi tài liệu khác:

- Các test chạy với **đồ giả**; phần DB, RLS và vòng khép kín cần Postgres + Redis tạm và mới chứng minh được khi chạy với chúng.
- Chưa có tin Zalo thật nào, lời gọi mô hình thật nào, hay máy Ubuntu thật nào đi qua hệ thống này.

## 13. Quyết định kiến trúc còn mở

Việc cần chủ phòng khám hoặc bác sĩ quyết định (cờ đỏ, phân quyền, persona xác minh, trấn an tự động, nhắc trước khi duyệt mẫu, trần 10, thời hạn lưu theo NĐ 13/2023, vị trí server, lưu tệp, webhook HTTPS, MCP cho bệnh nhân): SCOPE-AI01 mục 9. Phần kỹ thuật còn mở:

- **Chọn account khi nhiều account cùng loại kênh trong một phòng khám**: hiện gửi tin đã duyệt chọn account đầu tiên theo id đang chạy. Cần gắn account với hội thoại.
- **Một worker mỗi phòng khám hay chung**, và tiến trình nào sở hữu account Zalo nào.
- **Liên kết phiên bệnh nhân với `clinic.patient`** (vai trò `patient` rỗng); cần cho ứng dụng bệnh nhân gọi API này.
- **Đặt lịch của agent**: hiện là đề xuất; cần chủ phòng khám xác nhận quy trình.
- **Lưu tệp**: volume cục bộ hay object storage (cũng là việc mở ở SCOPE).
- **Khôi phục sao lưu và WAL liên tục**; UPS.
- **Nối eval vào `make test`**: `evals/` hiện chạy bằng lệnh riêng.
- **Sửa tài liệu hạ tầng còn nói "chờ gói G/E/C2"**: sau khi tích hợp, `infra/README.md` và đầu `docker-compose.yml` vẫn ghi worker chờ gói G, frontend chờ gói E, cầu nối chờ gói C2, trong khi các gói đó đã vào nhánh; và bảng dịch vụ của `infra/README.md` còn ghi các gói đó là điều kiện cần (cầu nối: `package.json` và `pnpm-lock.yaml` nay đã có). Lượt tài liệu này không sửa `infra/` (ngoài phạm vi), nên việc chỉnh các dòng đó để lại.
- **Migration**: gói mới thêm migration riêng và có nhiều đầu; `g_0005_merge_heads` đã gộp; gói sau phải gộp tiếp.
- **Ảnh Docker của cầu nối có vẻ không dựng được (đọc mã, chưa thử build)**: `infra/docker/bridge.Dockerfile` chạy `pnpm run build` nhưng `package.json` của cầu nối chỉ có `start` (chạy `tsx src/index.ts`) và không có `build`; `pnpm prune --prod` cũng sẽ gỡ `tsx` nếu nó là devDependency. Cần C2 và F thống nhất (thêm script `build` hoặc sửa Dockerfile). Chưa có bằng chứng nào về việc cầu nối chạy ngoài test của chính nó (profile compose `bridge` hay `pnpm start`).
