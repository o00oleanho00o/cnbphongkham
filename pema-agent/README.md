# pema-agent

Agent chăm sóc khách hàng (CSKH) bằng chữ qua Zalo cho Pema Digital Clinic, và CRM phòng khám phía server, trong một codebase:

1. **Bản dịch Python của [zalo-agent](https://github.com/vuhai2002/zalo-agent)** (MIT, TypeScript): kênh Zalo, vòng lặp agent, persona, công cụ, bộ nhớ, kho tri thức, bộ lập lịch, MCP client, kế toán token.
2. **CRM phòng khám** (Patient 360, lịch hẹn, việc chăm sóc, Inbox, hàng chờ duyệt) và **một FE Next.js** cho cả vận hành lẫn cấu hình AI.

**Một hệ thống, một phòng khám** (nhánh `feat/single-tenant`): mỗi bản cài phục vụ đúng MỘT phòng khám, có server, Postgres, Redis, tài khoản Zalo và khóa mã hóa riêng (yêu cầu bảo mật của phòng khám, bệnh viện, ngân hàng). Không còn RLS, không còn mã phòng khám khi đăng nhập hay trên đường dẫn webhook; một phòng khám vẫn có nhiều tài khoản Zalo. Muốn phục vụ phòng khám thứ hai thì dựng một bộ mới hoàn toàn ([infra/README.md](infra/README.md), mục "One system, one clinic"). Hai nhánh song song, xem mục "Hai nhánh song song" bên dưới.

Zalo là kênh ra khách. Giai đoạn này chỉ CSKH bằng chữ. Có hai hồ sơ chính sách: `staff_assistant` (giống zalo-agent gốc) và `patient_channel` (an toàn lâm sàng: mọi tin ra khách do người duyệt, cờ đỏ đến bác sĩ trước khi gọi mô hình, che PII, xác minh danh tính). Dữ liệu trong repo là **hư cấu**.

> **Trạng thái trung thực.** Mã và test hoàn thành với **đồ giả** (mô hình giả, client Bot API giả, cầu nối giả) và với Postgres + Redis tạm. **Chưa chạy** với Zalo thật, mô hình thật, Ollama cài trên Ubuntu thật, sao lưu mã hóa age/gpg, hay thiết bị thật cho FE. Chi tiết: [SCOPE-AI01 mục 8](docs/SCOPE-AI01.md#8-điều-chưa-kiểm-chứng). Tài khoản Zalo cá nhân là kênh **không chính thức** có rủi ro bị khóa; mặc định tắt.

## Tài liệu (đọc theo thứ tự)

| Tài liệu | Nội dung |
|---|---|
| [docs/PLAN-AI01.md](docs/PLAN-AI01.md) | Mục tiêu, kiến trúc kế hoạch, gói việc, hồ sơ chính sách |
| [docs/CONTRACTS-AI01.md](docs/CONTRACTS-AI01.md) | Hợp đồng giữa các gói, thư mục sở hữu, quy ước |
| [docs/SCOPE-AI01.md](docs/SCOPE-AI01.md) | Phạm vi, quyết định đã chốt, điều chưa kiểm chứng, **việc mở cần chủ phòng khám/bác sĩ quyết** |
| [docs/SPEC-AI01.md](docs/SPEC-AI01.md) | Hành vi, use case, tiêu chí nghiệm thu và bằng chứng, phân quyền |
| [docs/MODULEMAP-AI01.md](docs/MODULEMAP-AI01.md) | Module, gói sở hữu, ranh giới import |
| [docs/ARCH-AI01.md](docs/ARCH-AI01.md) | Tiến trình, DB, luồng tin, kênh, an toàn, triển khai; mục 14: hai nhánh song song (đa phòng khám và một phòng khám); mục 16: hộp thư dùng chung (gói O) |
| [docs/PORT-MAP.md](docs/PORT-MAP.md) | Mỗi file zalo-agent → module Python; cuối file có "Khác biệt so với PORT-MAP ban đầu" |
| [infra/README.md](infra/README.md), [infra/ubuntu/HUONG-DAN-UBUNTU.md](infra/ubuntu/HUONG-DAN-UBUNTU.md) | Compose, role DB, sao lưu; hướng dẫn Ubuntu + Ollama + Tailscale |
| [frontend/README.md](frontend/README.md), [backend/bridges/zalo-personal/README.md](backend/bridges/zalo-personal/README.md), [evals/README.md](evals/README.md) | FE và mock; cầu nối Zalo cá nhân và rủi ro; eval với mô hình thật |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Bản quyền zalo-agent và zca-js (MIT) |

Quy tắc chung của repo: [AGENT.md](../AGENT.md) và [ARCH-PB01](../docs/ARCH-PB01.md) ở thư mục gốc.

## Sơ đồ

```
Zalo ─► webhook (api, FastAPI, role be_app) ─► gộp tin ─► Redis TurnQueue ─► worker (role agent_worker)
Zalo cá nhân ─► cầu nối Node (zca-js, tuỳ chọn) ─► webhook                      │ vòng lặp agent, tool, hook chính sách
Nhân viên ─► Next.js ─► api (OpenAPI là hợp đồng)                                └─► ChannelPort.send_text
                                                                     (patient_channel: người duyệt trước khi gửi)
Postgres (MỘT phòng khám): clinic.* (CRM) | clinic_agent.* (cửa duy nhất của agent) | agent.* (engine, pgvector)
Redis: hàng đợi lượt, khoá thread, gộp tin, khoá lịch      LLM: Ollama / llama-server trên PC GPU (Qwen3-8B, bge-m3)
```

| Đường dẫn | Nội dung |
|---|---|
| `backend/packages/contracts` | `pema_contracts`: DTO, `ChannelPort`, các port giữa gói, đồ giả |
| `backend/apps/api/pema` | ứng dụng: `channels`, `middleware`, `agent`, `conversation`, `knowledge`, `scheduler`, `mcp`, `documents`, `images`, `video`, `config`, `clinic`, `policy`, `api`, `composition`, `workers`, `shared`, `core` |
| `backend/apps/api/alembic` | DDL (`0001` clinic, `0002` agent, `0003` clinic_agent, các migration của từng gói, `g_0005` và `h_0008` gộp đầu nhánh, `st_0009_single_tenant`: một phòng khám, bỏ RLS) |
| `backend/apps/api/openapi.json` | hợp đồng API (sinh bằng `make openapi`) |
| `backend/bridges/zalo-personal` | cầu nối Node cho tài khoản Zalo cá nhân (tuỳ chọn, cờ tắt) |
| `frontend` | Next.js App Router, backend giả để chạy không cần dịch vụ nào |
| `infra` | docker-compose, `.env.example`, script role/migrate/sao lưu, hướng dẫn Ubuntu |
| `kb-samples`, `evals` | tài liệu da liễu hư cấu; 17 kịch bản gốc + bộ ca CSKH |

## Chạy

Cần `uv` (Python 3.12+), `pnpm` (Node 22), Docker. Chạy từ thư mục `pema-agent/`. Không có `make` (Windows thuần) thì chạy tay các lệnh trong từng công thức của `Makefile`.

### Cài và kiểm tra

```
make setup        # uv sync --all-packages; pnpm install (frontend)
make lint         # ruff, ruff format --check, pyright strict, import-linter
make test         # pytest; test cần DB/Redis bị BỎ QUA nếu thiếu biến môi trường
```

`make test` không đặt biến nào **không** kiểm vai trò và grant của DB, ràng buộc một phòng khám hay vòng khép kín. Để chạy đủ, dùng một Postgres + pgvector và một Redis **tạm** (không bao giờ trỏ vào DB có dữ liệu cần giữ: fixture xóa mọi schema Pema trong đó rồi chạy lại migration):

```
docker run -d --name pema-pg-test -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema \
    -p 127.0.0.1:55432:5432 pgvector/pgvector:pg17
docker run -d --name pema-redis-test -p 127.0.0.1:56379:6379 redis:7-alpine
export PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:55432/pema
export PEMA_TEST_REDIS_URL=redis://127.0.0.1:56379/0
make test         # nay gồm test đánh dấu db và redis, và kịch bản vòng khép kín
```

Kiểm riêng từng phần:

```
cd backend && uv run pytest apps/api/tests/policy                  # chính sách: cờ đỏ, PII, xác minh
cd backend && uv run pytest apps/api/tests/integration             # vòng khép kín (cần DB + Redis)
cd backend && uv run pytest ../evals                                # eval với mô hình giả (cũng nằm trong make test)
cd backend/bridges/zalo-personal && pnpm install && pnpm test      # cầu nối (không bao giờ đăng nhập Zalo)
cd frontend && pnpm lint && pnpm typecheck && pnpm test
make openapi && make types   # sinh lại openapi.json rồi kiểu TypeScript
```

### FE với backend giả (không cần dịch vụ nào)

```
cd frontend
pnpm install
pnpm dev:mock     # backend giả :4010 + next dev :3000
```

Mở `http://127.0.0.1:3000`, đăng nhập bằng email và mật khẩu `demo1234` (không còn ô phòng khám), một trong `owner@pema.test`, `manager@pema.test`, `doctor@pema.test`, `cs@pema.test`, `reception@pema.test` (người dùng hư cấu của mock). `pnpm shots` chụp mọi màn ở 5 viewport (cần mock đang chạy; thất bại nếu tràn ngang). Mock bám đúng `openapi.json` (có test hợp đồng). Đây **không** phải backend thật và chưa kiểm trên thiết bị thật.

### Stack bằng Docker Compose

```
make infra-secrets   # tạo infra/.env với bí mật ngẫu nhiên (từ chối ghi đè); sao lưu ngoại tuyến PEMA_SECRET_ENCRYPTION_KEY; đặt PEMA_CLINIC_NAME
make infra-config    # kiểm file compose với mọi profile
make up              # postgres + pgvector, redis, migrate (một lần: role + alembic upgrade heads, tạo MỘT phòng khám từ PEMA_CLINIC_NAME, kiểm đúng một dòng), api  → /healthz
make ps
make up-app          # thêm worker và frontend (profile app)
make up-ollama       # thêm container Ollama có GPU NVIDIA (hoặc cài Ollama trực tiếp, xem hướng dẫn Ubuntu)
make down
```

Không có profile `worker` thì API nhận webhook và xếp lượt nhưng không ai chạy lượt. Tham số mô hình (`LLM_BASE_URL`, `LLM_MODEL=pema-chat`) và tuỳ chọn mạng (`PEMA_*_BIND`, chỉ loopback theo mặc định) ở `infra/.env.example`. Dữ liệu mẫu hư cấu cho phòng khám của bản cài: `uv run python -m pema.clinic.actions.seed_demo` (xem docstring của module; không có mật khẩu mặc định trong repo). Danh mục sản phẩm của phòng khám (115 dòng, dữ liệu thật, không phải dữ liệu mẫu) nạp một lần bằng `uv run pema catalog import <đường dẫn>/product-catalog.json [--source-name danhsach.xlsx] [--source-sha256 <SHA-256 của file Excel>]` (idempotent: chạy lại cùng file không đổi gì); ứng dụng không đọc thư mục `prototype/` khi chạy. Bot Zalo, QR cho tài khoản cá nhân, persona và KB cấu hình ở trang quản trị AI của FE.

Tài chính PB02 (U6) chạy trong cùng API: `/api/v1/finance/*` (tổng quan theo vai trò, lượt thủ thuật và người thực hiện, duyệt/hủy, chốt tháng và xác nhận đã chi, phiếu thu có mã chống thu trùng, thông báo của chủ, CSV) trên các bảng `clinic.invoice|payment|procedure_entry|procedure_entry_person|finance_period|finance_notification` (migration `u6_0010_finance`). Vai trò lấy từ phiên đăng nhập, không có header giả lập; kế toán chưa có vai trò riêng nên do `manager` đảm nhiệm. `prototype/finance_server.py` và `prototype/finance/` vẫn nằm trong repo nhưng FE mới không dùng; MISA/hóa đơn điện tử chưa làm.

## Ứng dụng nhân viên hợp nhất (gói U)

Một FE Next.js (`frontend/`) thay cho `prototype/clinic-web`: cùng thứ tự menu và nhãn tiếng Việt của web cũ (Tổng quan, Hôm nay, Điều phối lịch, Tìm bệnh nhân, Theo dõi, Ảnh trước / sau, Bác sĩ & phòng, Dịch vụ, Thu ngân, Tài chính & tiền thủ thuật, Hỏi Pema, Hướng dẫn), thêm Zalo & CSKH, Care agent và Quản trị agent giữ nguyên. Chạy thử không cần dịch vụ nào: `cd frontend && pnpm dev:mock`, đăng nhập `owner@pema.test` / `demo1234` (mock có dữ liệu mẫu của mọi màn). Chạy thật: `make up-app` (backend + worker + FE); nạp danh mục sản phẩm một lần bằng `pema catalog import` (đoạn trên) và dữ liệu mẫu bằng `seed_demo`; đổi tài khoản mẫu trước khi dùng.

Kiểm trước khi báo xong một thay đổi giao diện: `cd frontend && pnpm check` (lint, typecheck, format, vitest, `pnpm inventory`, rồi `pnpm smoke` và `pnpm visual` với `pnpm dev:mock` đang chạy; `CHECK_SKIP_BROWSER=1` bỏ hai bước trình duyệt và báo cáo phải nói rõ). Màu và cỡ chữ lấy từ `src/ui/tokens.css` (`pnpm tokens` sinh `tokens.json` cho KMP); `FEATURE-INVENTORY.md` là danh sách tính năng đóng băng. Ảnh đối chiếu với web cũ: `frontend/visual-ref/{old,new}` (git-ignored; sinh lại bằng `web-shots.cjs` và `pnpm visual`). Bằng chứng và khoảng trống còn lại: [docs/PARITY-AI01-U.md](docs/PARITY-AI01-U.md).

Còn nằm trong repo nhưng **không còn dùng** (quyết định xóa là của chủ phòng khám): `prototype/clinic-web`, `prototype/finance/*`, `prototype/finance_server.py` và `finance_test.py` (bản dịch Python của luật tài chính có test tương đương ở `backend/apps/api/tests/clinic/test_finance_equivalence.py`), `prototype/shared/*.js` của Clinic Web. Web Patient Mobile giữ nguyên cho ứng dụng bệnh nhân.

Ảnh Docker của cầu nối (`bridge` profile) và của FE đã dựng thật và khởi động thử (không cần Zalo thật); cầu nối chạy bằng tsx, không có bước build, và chỉ lắng nghe trong mạng compose.

## Cập nhật trực tiếp và hiện diện (gói ST-R)

Màn Inbox, "Việc hôm nay" và "Hàng đợi duyệt" tự tải lại khi có thay đổi, và hội thoại cho biết đồng nghiệp nào đang xem hoặc đang trả lời. Chỉ là cảnh báo, không khóa gì.

| Route | Việc |
|---|---|
| `GET /api/v1/events` | Server-Sent Events cho nhân viên đã đăng nhập. Mỗi sự kiện là JSON `{"type": "inbox.changed" \| "tasks.changed" \| "review.changed" \| "presence.changed", "id": "<uuid hoặc null>"}`; không bao giờ có nội dung tin, tên hay số điện thoại. Comment `: keep-alive` mỗi 15 giây; 429 quá 5 luồng mỗi người; 503 khi Redis hỏng (FE chuyển sang tải lại định kỳ). |
| `POST /api/v1/conversations/{id}/presence` | Nhịp 15 giây `{"state": "viewing" \| "replying"}`; mục hết hạn sau 30 giây. 204 cả khi Redis hỏng. |
| `DELETE /api/v1/conversations/{id}/presence` | Rời hội thoại. |
| `GET /api/v1/conversations`, `GET/PATCH /api/v1/conversations/{id}` | Có thêm `viewers: [{user_id, name, state}]`, không gồm chính người gọi. |

Worker và API là hai tiến trình; chúng gặp nhau qua kênh Redis pub/sub `pema:live:<clinic_id>` (package `pema.live`). Chi tiết: [CONTRACTS-AI01 mục 11](docs/CONTRACTS-AI01.md), [ARCH-AI01 mục 15](docs/ARCH-AI01.md), [SECURITY-REVIEW-AI01 mục 8](docs/SECURITY-REVIEW-AI01.md).

## Giao việc cho đồng nghiệp ("Phụ trách")

| Điểm cuối | Ai gọi | Ghi chú |
|---|---|---|
| `GET /api/v1/staff/assignable` | mọi nhân viên đã đăng nhập (kể cả lễ tân, CSKH) | `[{id, name, role}]` của nhân viên **đang hoạt động** có vai trò làm được hội thoại và việc CSKH (chủ, quản lý, bác sĩ, CSKH; không lễ tân), A-Z theo tên; không email, SĐT, hash, lần đăng nhập cuối; 60 lần/phút mỗi người; 401 khi chưa có phiên |
| `PATCH /api/v1/conversations/{id}` (`assigned_user_id`) | quyền `conversation.reply` | giao cho đồng nghiệp hoặc `null` (chưa giao); thành công thì phát `inbox.changed` tới các màn hình khác (mục trên) |
| `POST /api/v1/crm/tasks/{id}/resolve` (`owner_user_id`) | quyền `crm_task.resolve` | người phụ trách của việc CSKH |
| `POST/PATCH /api/v1/patients` (`doctor_id`, `cs_owner_id`) | quyền `patient.write` | bác sĩ điều trị, CSKH phụ trách hồ sơ |

Mọi nơi nhận người được giao chạy chung một kiểm tra phía máy chủ (`pema/clinic/actions/assignees.py`): người đó phải thuộc bản cài, đang hoạt động và có vai trò giao được, nếu không là 422 với cùng một câu trả lời (không lộ tài khoản nào tồn tại hay bị khóa). Dòng audit ghi id người giao trước và sau (không ghi tên). Quy tắc chọn vai trò và mục SEC-60 đến SEC-63 ở `docs/SECURITY-REVIEW-AI01.md`.

## Hộp thư dùng chung: một danh tính, nhiều người trực (gói O)

Khách chỉ nói chuyện với **danh tính của phòng khám** (ví dụ "Long" trên Zalo). Nhân viên **không bao giờ nhắn khách từ Zalo cá nhân**: họ trả lời trong Pema, và tin đi chỉ hiện danh tính (không tên người, không chữ ký). Zalo cá nhân của nhân viên chỉ **nhận thông báo không có thông tin cá nhân** (mã ngắn, tên danh tính, mức khẩn, một câu tóm tắt mẫu, đường dẫn cần đăng nhập). Thiết kế đầy đủ: [ARCH-AI01 mục 16](docs/ARCH-AI01.md); route và quyền: [CONTRACTS-AI01 mục 12](docs/CONTRACTS-AI01.md); rủi ro: [SECURITY-REVIEW-AI01 mục 11](docs/SECURITY-REVIEW-AI01.md) (SEC-64 đến SEC-78).

### Người trực mới: bắt đầu như thế nào

1. **Đăng nhập** Pema bằng tài khoản được chủ hay quản lý cấp. Chỉ bốn vai trò làm việc với hội thoại: chủ, quản lý, bác sĩ, CSKH. Lễ tân và kế toán không nhận và không gửi tin cho khách.
2. **Inbox** có ba thẻ: "Chờ nhận" (chưa ai phụ trách), "Của tôi", "Tất cả"; lọc được theo danh tính. Bấm **Nhận** để giữ một hội thoại: từ lúc đó chỉ bạn trả lời được, đồng nghiệp vẫn đọc được. Viết câu trả lời đầu tiên cho một hội thoại chưa ai nhận cũng là nhận.
3. Hội thoại do đồng nghiệp giữ hiện "<Tên> đang trả lời — Tiếp quản?". **Tiếp quản** cần ghi lý do; người cũ, người mới và nhóm đều được báo, lịch sử phụ trách có thêm một dòng. **Trả lại** đưa hội thoại về hàng chờ (hoặc về cho trợ lý chăm sóc khi bệnh nhân đang ở trạng thái nhân viên xử lý). Hết ca thì quản lý bấm "Hết ca" cho bạn: các hội thoại đang mở chuyển cho người đang trực danh tính đó hoặc về hàng chờ.
4. **Lịch trực** (`/admin/roster`, chủ và quản lý nhập, mọi người trực xem được): ai phụ trách danh tính nào, thứ nào, giờ nào.
5. **Nhận chuông trên Zalo cá nhân, làm một lần** (`/me/notifications`): bấm nút liên kết Zalo, nhận một mã 8 ký tự có hiệu lực 10 phút, nhắn đúng mã đó từ Zalo cá nhân của bạn tới **tài khoản thông báo nội bộ** của phòng khám. Pema xác nhận lại bằng một tin. Từ đó, nếu một thông báo dành cho bạn chưa được xác nhận sau 3 phút (cài đặt của phòng khám), chuông Zalo sẽ rung; tin khẩn rung kể cả trong giờ yên tĩnh bạn đặt. Gỡ liên kết bất cứ lúc nào ở cùng màn hình. Tin bạn nhắn tới tài khoản nội bộ ngoài mã liên kết không được đọc và không bao giờ vào Inbox khách.
6. **Push trên ứng dụng di động: chưa có.** Phía máy chủ đã sẵn (đăng ký thiết bị, nhà cung cấp giả để thử, nhà cung cấp thật đang tắt) nhưng `pema-kmp` chưa có mã nhận push và phòng khám chưa có thông tin FCM/APNs. Hiện chuỗi thật là: trong ứng dụng (trang "Thông báo của tôi", có liên kết ở thanh trên), rồi Zalo cá nhân, và nhóm Zalo của đội.

Quy tắc cho phòng khám (cũng ở [AGENT.md](../AGENT.md)): nhân viên không nhắn khách từ tài khoản cá nhân; mọi tin tới khách đi qua danh tính của Pema; Zalo cá nhân chỉ nhận thông báo không có thông tin cá nhân. Mã không chặn được việc ai đó tự mở Zalo cá nhân và nhắn khách (SEC-65), nên đây cũng là việc đào tạo.

Phần của gói M (vòng chăm sóc) chưa nối vào đây: cổng `StaffNotify` và `SlaScheduler` đã có adapter nhưng chưa được đăng ký, cầu nối `CareAssignmentBridge` và thứ tự lịch trực cho routing cũng vậy (gói M7). Cho tới lúc đó, hộp thư của người trực (nhận, tiếp quản, gửi, thông báo trong ứng dụng, chuông và nhóm) chạy độc lập.

### Đo và kiểm tra gói O

`evals/ops/` (bộ tải 200 hội thoại một danh tính, năm người trực, bộ đua, bộ quét bảo mật): số đo và cách chạy ở [evals/ops/report.md](evals/ops/report.md). Chạy:

```bash
cd pema-agent/backend
PYTHONPATH=.. uv run python -m evals.ops.run_eval                                   # không cần cơ sở dữ liệu: hàng đợi, chuỗi thông báo, leo thang
PYTHONPATH=.. PEMA_EVAL_OPS_DATABASE_URL=postgresql+psycopg://... uv run python -m evals.ops.run_eval   # thêm phần 200 hội thoại thật (CSDL TẠM: bị xóa và dựng lại)
PEMA_TEST_DATABASE_URL=postgresql+psycopg://... uv run pytest -c pyproject.toml --rootdir . ../evals/ops
```

## Quy tắc áp dụng khắp nơi

- Phía agent chạm phòng khám **chỉ** qua `pema.clinic.actions` (import-linter); trong DB role `agent_worker` không có quyền gì trên `clinic.*` (chỉ view/hàm của `clinic_agent`).
- Mọi bảng có `clinic_id` làm mã cài đặt cố định của MỘT phòng khám; không RLS, không ngữ cảnh phòng khám: mở công việc bằng `ClinicDatabase.session()`, lấy mã bằng `get_installation_clinic_id(db)`, SQL dùng `ctx.the_clinic_id()` (CONTRACTS-AI01 mục 10). Ranh giới DB là grant của `be_app`/`agent_worker`; cách ly giữa các phòng khám là hạ tầng riêng cho từng phòng khám.
- Thời gian trên đường truyền là ISO 8601 có `+07:00`. Giao diện tiếng Việt.
- Không commit `.env`, token, số điện thoại hay tên thật. Không PII trong log.
- Không bao giờ tự gửi tin cho bệnh nhân trong `patient_channel` mà không có người duyệt; agent chỉ đề xuất lịch; sinh nhật không tự gửi; `marketingOptOut` chặn tiếp thị.
- Chế độ Zalo cá nhân chỉ bật khi đặt `PEMA_ZALO_PERSONAL_ENABLED` và đã quét QR; dùng **tài khoản phụ**.

## Hai nhánh song song

| | `feat/ai-agent-backend` | `feat/single-tenant` |
|---|---|---|
| Mô hình | nhiều phòng khám trong một CSDL, RLS theo `clinic_id` | MỘT phòng khám mỗi bản cài, không RLS; `clinic.clinic` đúng một dòng |
| Đăng nhập | phòng khám (slug) + email + mật khẩu | email + mật khẩu |
| Webhook Zalo | `/api/v1/webhooks/zalo-bot/{clinic}/{account}` | `/api/v1/webhooks/zalo-bot/{account}` (cầu nối tương tự) |
| Cấu hình | không có biến phòng khám | `PEMA_CLINIC_NAME`, `PEMA_CLINIC_ID` (tùy chọn) |
| Phòng khám thứ hai | thêm dòng trong cùng CSDL | một bộ hạ tầng mới hoàn toàn |

Cả hai nhánh được giữ. **Tính năng về sau làm trên `feat/single-tenant` trước**; nhánh đa phòng khám chỉ nhận bản backport khi có yêu cầu cụ thể, và hai nhánh không gộp vào nhau (migration `st_0009` bỏ RLS). Chi tiết và lý do: [ARCH-AI01 mục 14](docs/ARCH-AI01.md), quyết định: [SCOPE-AI01 mục 7](docs/SCOPE-AI01.md), hệ quả bảo mật: [SECURITY-REVIEW-AI01 mục 7](docs/SECURITY-REVIEW-AI01.md). Việc mở: ứng dụng bệnh nhân (web, KMP) và client khác gọi đăng nhập theo slug hoặc đường webhook có đoạn phòng khám phải đổi theo (SCOPE-AI01 mục 9, việc 12).

## Giấy phép và nguồn gốc

Phần engine là bản dịch từng module của zalo-agent (MIT, © 2026 Vu Van Hai) và dùng `zca-js` (MIT); thông báo nguyên văn ở [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Cách quan hệ phái sinh hoạt động và bản tham chiếu nằm ngoài repo: [ARCH-AI01 mục 11](docs/ARCH-AI01.md#11-quan-hệ-phái-sinh-và-giấy-phép).
