# Pema Agent — Module Map AI01

Đọc sau [SPEC-AI01](SPEC-AI01.md). Bản đồ này đi từ nền ẩn đến lớp nhìn thấy, như MODULEMAP-PB01, và ghi **gói sở hữu** từng module (tên gói theo [PLAN-AI01](PLAN-AI01.md) mục 6; một gói chỉ sửa thư mục của mình). Đối chiếu với cây file thật ngày 2026-10-02, commit `1ce6cca`. Ánh xạ từng file TypeScript của zalo-agent ở [PORT-MAP](PORT-MAP.md); mục "Khác biệt so với PORT-MAP ban đầu" ở cuối file đó liệt kê chỗ thực tế lệch với kế hoạch.

Đường dẫn Python viết tắt `pema/...` là `backend/apps/api/pema/...`; test ở `backend/apps/api/tests/...`.

## Gói và phạm vi

| Gói | Phạm vi | Ghi chú |
|---|---|---|
| A | Hợp đồng (`pema_contracts`), khung, công cụ, DDL, PORT-MAP, tiện ích dùng chung | làm trước, mọi gói khác dựa vào |
| B1 | Lõi phòng khám: auth, RBAC, audit, hành động và route bệnh nhân/lịch/hội thoại/hàng duyệt/đồng ý | |
| B2 | Luật CRM → việc và job | |
| C1 | Zalo Bot API, middleware, hàm nhập dùng chung | |
| C2 | Zalo cá nhân, cầu nối Node, đường gửi/lượt dùng chung | |
| D1 | Engine agent, nhà cung cấp LLM, tuning, eval | |
| D2 | Hội thoại, bộ nhớ, kho account/agent | |
| D3 | Kho tri thức (KB) | |
| D4 | Công cụ, tài liệu, ảnh, video, web | |
| D5 | MCP client | |
| S | Bộ lập lịch | |
| P | Chính sách: hồ sơ, cờ đỏ, PII, xác minh | |
| E | FE Next.js | |
| F | Hạ tầng và tài liệu | |
| G | Tích hợp: composition, tiến trình worker, kịch bản vòng khép kín, review | |

## Nền ẩn

| Module | Trách nhiệm | Hợp đồng | Gói |
|---|---|---|---|
| `backend/packages/contracts` (`pema_contracts`, 25 file) | DTO pydantic, `ChannelPort`, `AgentEngine`, `PolicyHooks`, `ToolRegistry`, `SchedulerPort`, `AgentFacingClinicActions`, `ConversationStore`, các bản giả (`testing`) | Mọi seam giữa gói là Protocol ở đây; là lá, không import gói nào | A (+ G cho các thêm seam) |
| `pema/core` | `ClinicDatabase.session(clinic_id)` (đặt `app.clinic_id` cho giao dịch → RLS), vòng lặp sự kiện selector cho Windows | Không có ngữ cảnh phòng khám thì không có hàng | A |
| `pema/shared` (27 file) | Logger che PII, giờ VN, múi giờ, bộ tuần tự lỗi an toàn, chặn địa chỉ riêng/SSRF, tải xuống an toàn, đọc zip/xml có trần, chờ có điều kiện | | A, D1, D2, D3, D4 |
| `pema/config` (20 file) | `Settings` (`PEMA_*`), 72 tham số tuning, mã hóa bí mật, account/agent store, cài đặt LLM/ảnh/tool/thị giác, kho `agent.runtime_settings` | `get_tuning`, `bot_time_zone` | A, D1, D2, D4, G |
| `backend/apps/api/alembic/versions` | `0001` clinic, `0002` agent, `0003` clinic_agent; `b1_0004` phiên + Inbox; `b2_0001` dấu giao thức CRM; `s_0004` runtime bộ lập lịch; `p0001` liên kết danh tính; `g_0005` gộp đầu nhánh | Không sửa `0001..0003`; bảng mới có `clinic_id`, RLS, grant | A + từng gói + G |
| Role DB `be_app`, `agent_worker` | `be_app`: DML trên `clinic.*` và `agent.*`, `audit_log` chỉ chèn/đọc. `agent_worker`: DML `agent.*`, đọc view `clinic_agent`, EXECUTE hàm `clinic_agent`; **không có gì trên `clinic.*`** | Không sở hữu bảng nên RLS áp dụng | A (tạo) + `infra/scripts/bootstrap-roles.sh` (F, mật khẩu) |

## Lõi phòng khám (`pema/clinic`, 48 file)

| Module | Trách nhiệm | Gói |
|---|---|---|
| `clinic/models` | Bảng ORM: bệnh nhân, đợt điều trị, lịch, buổi, đồng ý, hội thoại/tin, `review_item`, mẫu tin, việc/hoạt động CRM, audit, phiên, danh tính kênh, cài đặt kênh | B1 |
| `clinic/domain` | Luật thuần: lịch (xung đột), hồ sơ, máy trạng thái `review_item` | B1 |
| `clinic/rbac` | Ma trận vai trò → quyền, `authorize`, mật khẩu argon2 | B1 |
| `clinic/audit` | Ghi audit và guard (mọi mutation có dòng audit) | B1 |
| `clinic/actions` | Hành động dùng chung cho route **và** agent: patients, patient_360, appointments, consents, conversations, crm_tasks, review_items, templates, outbound, `agent_facing` (cửa của agent), `seed_demo` (dữ liệu hư cấu) | B1 |
| `clinic/crm_rules` | Engine thuần mười luật, runner, sinh job, kho SQL, admin luật | B2 |

Nguồn JS: `prototype/shared/crm-data.js` và `crm-automation.js` (không phải zalo-agent). Đây là module hành vi tương đương được test.

## Kênh (`pema/channels`, 63 file; `pema/middleware`, 7 file)

| Module | Trách nhiệm | Gói |
|---|---|---|
| `channels/zalo_bot` | Client Bot API, parser update, listener/polling, webhook (chống trùng `update_id` ở `agent.channel_update_seen`), router, quản lý account | C1 |
| `channels/oa_api.py` | **Stub** Zalo OA/ZNS | C1 |
| `channels/zalo_personal` | `ChannelPort` cho tài khoản cá nhân; client cầu nối ký HMAC; QR; kết nối lại; kết bạn; `proactive_gate` (kill switch, cửa sổ, trần, khoảng cách); kho thông tin đăng nhập mã hóa | C2 |
| `channels/*.py` (pipeline) | Chuẩn hóa/tách/gửi theo phần, markdown→style, trả lời, `message_turn_processor` (xử lý một `TurnJob`) | C2 |
| `channels/{record_incoming_message, busy_wait_notice, payload_anomaly_watch, reply_target_tu_kenh}.py` | Hàm nhập dùng chung: ghi `agent.history` **và** Inbox | C1 |
| `channels/registry.py` | `InMemoryChannelRegistry` | A |
| `middleware` | Danh sách cho phép, gộp tin (debounce), giới hạn tốc độ, chuỗi chạy theo thread, nền Redis | C1 |
| `backend/bridges/zalo-personal` | Cầu nối Node 22 + Hono + `zca-js` 2.1.2; cờ tắt; trần riêng; breaker; kill switch dòng lệnh | C2 |

## Engine agent (`pema/agent`, 91 file; `pema/conversation`, 17 file)

| Module | Trách nhiệm | Gói |
|---|---|---|
| `agent/agent_loop.py` và phụ trợ | Vòng lặp tool tự viết, guard lặp tool, điều kiện dừng, ngân sách ngữ cảnh theo token, tiêm tin giữa lượt, trace | D1 |
| `agent/persona_*`, `prompt_leak_markers` | Persona, luật tool, dấu hiệu lộ prompt | D1 |
| `agent/providers` | `openai` (OpenAI-compatible: Ollama, llama-server), Anthropic, Gemini | D1 |
| `agent/tools` | Registry và 15 tool gốc; `clinic_tools.py` (ba tool phòng khám, qua `agent_facing`) | D4 (`clinic_tools`: G) |
| `conversation` | Lịch sử, bộ nhớ, tóm tắt cuộn, thread, danh bạ, usage/token, trace, ảnh mô tả, xóa phiên (`xoa_han_session`) | D2 |

## Tri thức, công cụ, MCP

| Module | Trách nhiệm | Gói |
|---|---|---|
| `knowledge` (30 file) | Trích an toàn docx/xlsx/pdf/txt/md (trần zip bomb, worker có timeout), chia đoạn, FTS Postgres + pgvector (`bge-m3`, 1024) + RRF, gắn KB vào agent, **chỉ trích tài liệu đã ký duyệt trong `patient_channel`** | D3 |
| `documents`, `images`, `video` | Tạo docx/xlsx từ DATA (không nhận mã), ảnh, tải video; tắt trong `patient_channel` | D4 |
| `mcp` | Kết nối HTTP, mặc định chặn theo từng agent, dấu vân tay chống thay đổi công cụ, cổng hồ sơ (`mcp_profile_gate`) | D5 |

## Bộ lập lịch (`pema/scheduler`, 32 file)

Parser lịch, tính lần chạy kế, vòng lặp, kho job/log chạy, sổ đếm tin chủ động nguyên tử, hàng đợi gửi có khoảng cách, thử chạy (trial), phục hồi, dấu im lặng, điền placeholder của mẫu chỉ khi đã xác minh. Gói S. Nền Redis cho khóa; `pg_readers` đọc `clinic_agent`.

## Chính sách (`pema/policy`, 12 file, gói P)

| Module | Trách nhiệm |
|---|---|
| `profiles` | Chọn hồ sơ (chặt hơn thắng), dựng `PolicyContext`, payload `GET /admin/policy/profiles` |
| `hooks` | `ClinicPolicyHooks`: tám hook, chạy theo cờ của hồ sơ |
| `redflags`, `text_normalize` | Bộ phát hiện cờ đỏ và chuẩn hóa chữ (bỏ dấu, kéo dài, phân cách) |
| `pii` | Che PII và khôi phục chỉ tên (`MaskVault`, `MaskSession`) |
| `identity` | Chuẩn hóa/băm SĐT, mã lễ tân, `IdentityLinker` |
| `identity_admin` | Phía nhân viên (xác nhận, từ chối, cấp mã); chạy ở API, `be_app` |
| `gateway` | Cửa `agent_worker` vào view/hàm `clinic_agent` |
| `review` | Dựng các `review_item` do chính sách mở |
| `turn_guard` | Thứ tự chuẩn của một lượt, như hàm tham chiếu |
| `testing` | Đồ giả trong bộ nhớ |

Gói P **thêm** `hooks`, `gateway`, `review`, `turn_guard`, `identity_admin`, `testing`, `text_normalize` so với ba file kế hoạch ban đầu (`profiles`, `redflags`, `pii`).

## API và tiến trình

| Module | Trách nhiệm | Gói |
|---|---|---|
| `pema/api` (41 file) | `router.py` gom route, `deps`, `errors`, xuất OpenAPI; routers mỏng gọi actions hoặc store; xác thực dashboard; webhook Zalo | A (khung), mỗi router có một chủ (CONTRACTS-AI01 mục 2) |
| `pema/composition` (8 file) | **Gốc ghép**: `runtime.build_runtime` tạo mọi đối tượng một lần mỗi tiến trình; `intake` (ngăn xếp Bot và cá nhân); `outbound` (gửi tin đã duyệt qua kênh đang chạy); `api_wiring` (lifespan, vòng CRM); `auth_bridge`; `adapters` | G |
| `pema/bootstrap.py` | `create_app()` (rẻ, không cần Redis hay DB); lifespan dựng mọi thứ | A, G |
| `pema/workers` (5 file) | `main` (điểm vào `python -m pema.workers.main`), `turn_worker`, `scheduler_worker`, `kb_ingest_worker` | G, C2, S, D3 |

## Ranh giới được máy kiểm tra (import-linter, `make lint`)

- `pema_contracts` là lá.
- `pema.clinic.domain` và `pema.clinic.actions` không import channels, api, agent, workers, middleware.
- Phía agent chạm `pema.clinic` **chỉ** qua `pema.clinic.actions`.
- Chỉ `bootstrap`, `api`, `workers` (và `composition`) import `pema.api` / `pema.workers`.
- Theo quy ước, chưa ép: `pema.scheduler` và `pema.channels` nhận engine dưới dạng `AgentEngine`, không import `pema.agent`.

## Giao diện (`frontend/`, gói E)

Next.js App Router, TypeScript, Tailwind v4, Be Vietnam Pro, màu Pema (`brand-500` `#0B4F94`). Menu lọc theo `GET /me`; đó là tiện ích, **không** là cơ chế kiểm soát (quyền do BE). Client gõ kiểu từ `openapi.json` (`openapi-typescript`).

| Vùng | Route |
|---|---|
| Vận hành | `/today`, `/inbox`, `/review`, `/patients`, `/patients/[id]`, `/templates` |
| Quản trị AI | `/admin/{overview, accounts, agents, agents/new, agents/[id], contacts, friends, threads, memory, kb, schedules, mcp, tools, tuning, tuning/[group], traces, logs, policy, auth}` |
| Phiên | `/login` |

`frontend/mock` là backend giả phục vụ cùng đường dẫn của `openapi.json`, có test hợp đồng để mock không lệch. Mã dịch từ `web/` của zalo-agent ở `src/components/admin/<vùng>` và `src/lib/admin/<vùng>`; mã Pema-only (không có bản gốc) ở `src/components/ops` và `src/lib/ops`, trang chính sách, công tắc kênh, cột ký duyệt KB, "Thử tìm".

## Hạ tầng, đánh giá, dữ liệu mẫu

| Thư mục | Nội dung | Gói |
|---|---|---|
| `infra/` | `docker-compose.yml` (postgres+pgvector, redis, migrate, api; profile worker/frontend/bridge/ollama/app), `docker/` (ba Dockerfile), `scripts/` (sinh bí mật, role, migrate, sao lưu/khôi phục, tải mô hình), `ubuntu/HUONG-DAN-UBUNTU.md` và `systemd/`, `.env.example`, `accounts.example.json` | F |
| `evals/` | Dịch 17 kịch bản gốc và bộ ca CSKH da liễu (có/không dấu, danh tính chưa xác minh, opt-out, sinh nhật); chạy với mô hình thật bằng tay, **chưa chạy** | D1, P |
| `kb-samples/` | Ba tài liệu da liễu hư cấu | D3 |
| `docs/` | PLAN, CONTRACTS, PORT-MAP, SCOPE/SPEC/MODULEMAP/ARCH-AI01 | A, F |

## Phụ thuộc giữa các lớp

```
Hợp đồng (pema_contracts) ─► tiện ích/config/core ─► clinic (domain→actions) ─► api routers ─┐
                                      │                         ▲                            │
                                      ├─► policy (hooks, gateway)│                            ├─► bootstrap / workers
                                      ├─► conversation, knowledge, mcp ─► agent (loop, tools) │   (composition ghép)
                                      ├─► scheduler ◄───────────── clinic.crm_rules          │
                                      └─► channels, middleware ─────────────────────────────┘
```

Mọi mũi tên đi qua Protocol trong `pema_contracts`; chỉ `composition` biết đối tượng thật.
