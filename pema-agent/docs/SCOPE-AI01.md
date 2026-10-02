# Pema Agent — Scope AI01

Trạng thái: mô tả hiện trạng mã trên nhánh `feat/ai-agent-backend` (commit tích hợp `1ce6cca`), viết ngày 2026-10-02 bởi gói F; **cập nhật cho nhánh `feat/single-tenant`: phạm vi là MỘT phòng khám mỗi bản cài** (mục 2, mục 7 quyết định 16, ARCH-AI01 mục 14 về hai nhánh song song). Luồng tài liệu: **SCOPE-AI01 → [SPEC-AI01](SPEC-AI01.md) → [MODULEMAP-AI01](MODULEMAP-AI01.md) → [ARCH-AI01](ARCH-AI01.md)**. Kế hoạch gốc là [PLAN-AI01](PLAN-AI01.md); hợp đồng giữa các gói là [CONTRACTS-AI01](CONTRACTS-AI01.md); bảng dịch file là [PORT-MAP](PORT-MAP.md).

Bộ tài liệu này cùng cấp với bộ PB01/PB02 trong `docs/` và theo cùng quy tắc của `AGENT.md`: chỉ ghi điều mã làm được, tách rõ "đã có test với đồ giả" khỏi "đã chạy thật", và mọi dữ liệu trong repo là hư cấu. Nơi nào chưa kiểm chứng, tài liệu nói thẳng là chưa kiểm chứng; danh sách đầy đủ ở mục 8.

## 1. Vấn đề và mục tiêu

Bệnh nhân hỏi phòng khám qua Zalo vào mọi giờ: hỏi chăm sóc sau laser, hỏi lịch, hỏi khi nào cần tái khám, và đôi khi nhắn một dấu hiệu nguy hiểm (chảy máu, sốt, mưng mủ, khó thở). Nhân viên chăm sóc khách hàng (CSKH) không trả lời kịp, trả lời mỗi người một kiểu, và việc nhắc theo mốc (D+1, D+3, D+7, D+30) đang là việc thủ công trong CRM01.

Pema Agent làm hai việc trong một codebase (`pema-agent/`):

1. **Engine agent CSKH bằng chữ qua Zalo**: bản dịch sang Python của `vuhai2002/zalo-agent` (TypeScript, MIT): kênh Zalo, vòng lặp agent, persona, công cụ, bộ nhớ, kho tri thức (KB), bộ lập lịch, MCP client, kế toán token.
2. **CRM phòng khám phía server**: hồ sơ, lịch hẹn, mốc chăm sóc, Inbox, hàng chờ duyệt, phân quyền, audit; cùng **một FE Next.js** cho cả vận hành lẫn cấu hình AI, để nhân viên không phải dùng nhiều ứng dụng.

Mục tiêu an toàn đi trước mục tiêu tiện lợi: agent soạn nháp, người duyệt rồi mới gửi cho bệnh nhân; dấu hiệu nguy hiểm đến bác sĩ trước khi có bất kỳ lời gọi mô hình nào.

## 2. Trong phạm vi

- **CSKH bằng chữ** với bệnh nhân qua Zalo. Tool ảnh, video, tài liệu, web vẫn được dịch đủ nhưng **tắt trong hồ sơ `patient_channel`**.
- **Hai hồ sơ chính sách** gắn với từng account và từng agent (mục 3). An toàn lâm sàng là hồ sơ, không phải việc xóa tính năng đã dịch.
- **Kênh Zalo**: Zalo Bot API (chính thức; polling hoặc webhook) và tài khoản Zalo cá nhân qua cầu nối Node dùng `zca-js` (không chính thức, có rủi ro bị khóa tài khoản, mặc định tắt). Zalo OA/ZNS chỉ là stub (mục 5).
- **Một phòng khám mỗi bản cài** (single-tenant): một bản cài phục vụ đúng MỘT phòng khám, có server, CSDL, Redis, khóa mã hóa và tài khoản Zalo riêng; một phòng khám có thể có nhiều tài khoản Zalo. Không còn nhiều phòng khám trên cùng hệ thống, không còn RLS, đăng nhập chỉ email và mật khẩu, webhook Zalo không có đoạn phòng khám.
- **CRM server**: đăng nhập JWT (email + mật khẩu), phân quyền theo ma trận ARCH-PB01 (deny by default), audit mọi thay đổi, role `be_app`/`agent_worker` với grant tối thiểu (không còn RLS, xem quyết định 16); bệnh nhân/Patient 360, lịch hẹn, hội thoại và Inbox, hàng chờ duyệt (`review_item`), đồng ý (consent), tin nhắn mẫu đã duyệt.
- **Luật CRM tự động**: mười luật của `crm-automation.js` thành engine Python sinh việc cho nhân viên và (khi cấu hình) job vào bộ lập lịch; `marketingOptOut` chặn tiếp thị; sinh nhật không bao giờ tự gửi.
- **Bộ lập lịch**: job `message` (từ mẫu đã duyệt) và `agent`, trần tin chủ động mỗi ngày, công tắc khẩn (kill switch), cửa sổ giờ gửi, khoảng cách giữa các tin, phục hồi sau lỗi.
- **Kho tri thức** tài liệu da liễu (tài liệu mẫu hư cấu trong `kb-samples/`) với tìm kiếm lai (từ khóa + vector) và dấu duyệt của bác sĩ.
- **FE Next.js** (mobile-first, tiếng Việt): Việc hôm nay, Inbox, Hàng đợi duyệt, Hồ sơ bệnh nhân (chỉ đọc), Tin nhắn mẫu; và quản trị AI (accounts/QR, agents/persona, model/tuning, tools, KB, lịch, MCP, usage/trace, log, chính sách).
- **Hạ tầng**: docker-compose (Postgres + pgvector, Redis, migrate, api, worker, frontend, bridge, Ollama, Caddy reverse proxy ở profile `proxy`), tác vụ xóa dữ liệu theo thời hạn lưu (`pema.retention`), role DB, sao lưu/khôi phục, hướng dẫn Ubuntu + Ollama + Tailscale.

## 3. Hai hồ sơ chính sách

Cột `patient_channel` là mặc định an toàn: account hoặc agent mới tạo nhận hồ sơ này; khi account và agent khác hồ sơ, **hồ sơ chặt hơn thắng** (`effective_profile_key`).

| | `staff_assistant` (giống zalo-agent gốc) | `patient_channel` (CSKH bệnh nhân) |
|---|---|---|
| Tin ra khách | Gửi thẳng | Vào `review_item`; người duyệt rồi hệ thống mới gửi |
| Job theo lịch | `message` và `agent` như gốc | Chỉ `message` từ mẫu đã duyệt; job `agent` chỉ soạn nháp |
| `save_memory` | Cho phép | Ẩn tool và chặn ghi với nội dung từ bệnh nhân |
| Tool ảnh/video/tài liệu/web, MCP | Theo cấu hình | Tắt (tool MCP bị chặn theo tiền tố `mcp__`) |
| Khách gửi ảnh/tệp | Đi qua | Gắn cờ Inbox (`media_flag`), không phân tích, chuyển người |
| Cờ đỏ | Không áp | Chuyển bác sĩ **trước khi gọi mô hình** |
| Che PII trước mô hình | Tuỳ chọn | Bắt buộc |
| Trần tin chủ động mỗi ngày | Theo (account, thread, ngày) | Theo (bệnh nhân, account, ngày) |
| `marketingOptOut`, sinh nhật | Không áp | Chặn tiếp thị; sinh nhật là việc nhân viên |
| Xác minh `zalo_uid` với hồ sơ | Không cần | Bắt buộc trước khi nêu tên, lịch hẹn hay thuốc |
| Trích KB | Mọi tài liệu | Chỉ tài liệu bác sĩ hoặc chủ phòng khám đã ký duyệt (`approved_by_clinical_owner`) |
| Tool phòng khám (`patient.get_care_context`, `appointment.book`, `escalation.create`) | Không nhận | Nhận |

Mọi cờ nằm trong dữ liệu `DEFAULT_PROFILES` (`pema_contracts.policy`); `ClinicPolicyHooks` chỉ làm theo cờ.

## 4. Người dùng và vai trò

Vai trò nhân viên theo `pema_contracts.roles`: chủ phòng khám (`owner`), quản lý (`manager`), bác sĩ (`doctor`), CSKH (`cs_staff`), lễ tân (`reception`). Vai trò `patient` hiện **không có quyền nào** trên các route nhân viên (chưa có liên kết phiên bệnh nhân với hồ sơ). Thu ngân/tài chính thuộc PB02, không nằm trong API này. Chi tiết phân quyền ở SPEC-AI01 mục 5. Bệnh nhân không dùng FE này: họ chỉ nhắn qua Zalo; ứng dụng bệnh nhân (web, KMP) của PB01 giữ nguyên và không đổi.

## 5. Kênh Zalo

| Kênh | Trạng thái | Ghi chú |
|---|---|---|
| Zalo Bot API | Đã dịch và nối vào tiến trình; **chưa chạy với bot Zalo thật** | Token bot nhập ở màn hình quản trị, lưu mã hóa AES-256-GCM. Mặc định `polling` (worker nghe); `webhook` cần địa chỉ HTTPS công khai. Hai chế độ loại trừ nhau ở phía Zalo. |
| Zalo cá nhân (cầu nối Node + `zca-js`) | Đã dịch; cờ tắt mặc định; **chưa chạy với tài khoản Zalo thật** | **Rủi ro khóa/cấm tài khoản và vi phạm điều khoản Zalo do chủ phòng khám chịu.** Chỉ dùng tài khoản phụ. Có trần riêng, kill switch, breaker. |
| Zalo OA / ZNS | **Stub** (`pema/channels/oa_api.py`, mọi hàm ném `NotImplementedError`) | Chưa có hợp đồng OA/ZNS. |

## 6. Ngoài phạm vi

- Ảnh lâm sàng, phân tích ảnh, video, bản ghi âm; mô hình thị giác trong `patient_channel`. Khách gửi ảnh thì chuyển người.
- Thanh toán, hóa đơn, tài chính (PB02), Vitech/MISA.
- Tinh chỉnh (fine-tuning) mô hình.
- **Tự gửi không có người duyệt** trong `patient_channel`; chẩn đoán tự động; tự đổi phác đồ; tự đặt lịch (agent chỉ *đề xuất*, nhân viên xác nhận).
- Nhắn tin sinh nhật tự động.
- **Nhiều phòng khám trên một hệ thống** (đa tenant) trên nhánh `feat/single-tenant`: ngoài phạm vi; phòng khám thứ hai là một bản cài khác hẳn (nhánh `feat/ai-agent-backend` còn mô hình đa phòng khám cũ, ARCH-AI01 mục 14).
- Ứng dụng bệnh nhân gọi API này; đồng bộ ngược sang prototype web/KMP của PB01.
- Chuyển nghiệp vụ pháp lý (Nghị định 13/2023) vào mã: mã giữ che PII, consent, audit, grant tối thiểu; trách nhiệm pháp lý là của chủ phòng khám.

## 7. Quyết định đã chốt

Nguồn: PLAN-AI01 mục 8 (2026-10-01), CONTRACTS-AI01 mục 7, và ghi chú trong mã.

1. Chưa có Zalo OA/ZNS; chỉ Bot API và tài khoản cá nhân. `oa_api.py` là stub.
2. PC chạy **Ubuntu cài hẳn**; LLM qua Ollama (Qwen3-8B Q5_K_M, nhúng `bge-m3`), sau chuyển llama-server (roadmap). **Từ 2026-10-02 tạm dùng API LLM bên thứ ba** (như zalo-agent), LLM local và embedding tạm tắt; xem PLAN-AI01 mục 8. Nội dung hội thoại rời hạ tầng phòng khám; `patient_channel` vẫn che PII trước LLM.
3. Vitech/MISA không đụng trong AI01. Giữ cả Zalo và ứng dụng bệnh nhân (web + KMP).
4. Bác sĩ trong đội duyệt mẫu tin, KB và nháp. Pháp lý thuộc chủ phòng khám.
5. Mặc định hồ sơ của account và agent là `patient_channel` (an toàn khi quên cấu hình).
6. **Trần tin chủ động mặc định 10 mỗi ngày** (`SCHEDULER_MAX_PROACTIVE_PER_DAY`); con số 60 của bản kế hoạch 1 bị bỏ. `clinic.channel_setting.daily_cap` đặt trần riêng theo kênh; số nhỏ hơn thắng.
7. Postgres thay SQLite; hai schema nghiệp vụ `clinic.*` và `agent.*`; agent chỉ vào dữ liệu phòng khám qua schema `clinic_agent` (view tối thiểu + hàm có audit).
8. Luật CRM chạy ở tiến trình API (vai trò `be_app`), job do bộ lập lịch của worker thực thi.
9. Mẫu tin (`clinic.message_template`) phải có dấu duyệt của bác sĩ mới dùng được cho job `message`.
10. Đặt lịch của agent là **đề xuất**; nhân viên xác nhận thì lịch mới được tạo (ghi trong `clinic_tools.py`: quyết định sản phẩm 2026-10-01).
11. Giữ nguyên giá trị Việt của enum lưu và hiển thị (`cho_xu_ly`, `da_ket_noi`, ...); thời gian ISO 8601 với `+07:00`.
12. **Phiên đăng nhập có hạn tuyệt đối** (`PEMA_SESSION_ABSOLUTE_DAYS`, mặc định 7, 1 đến 30) bên cạnh hạn trượt 480 phút; chủ phòng khám đặt lại mật khẩu nhân viên qua `POST /api/v1/admin/users/{user_id}/password` (quyền `admin.users`, chỉ chủ). Vòng tích hợp H, 2026-10-02.
13. **Có tác vụ xóa theo thời hạn lưu** (`pema.retention`; worker chạy scope `agent`, API chạy scope `clinic`), nhưng mặc định giữ dữ liệu lâm sàng và tin nhắn vô thời hạn; chỉ dữ liệu thuần kỹ thuật có đời ngắn. Không bao giờ xóa `clinic.audit_log`, bệnh nhân, lịch hẹn, đồng ý, mục duyệt đang mở.
14. **Truy cập công khai qua Caddy** (profile `proxy`, ba chế độ TLS `auto`/`internal`/`off`); chỉ Caddy publish 80/443, API chỉ tin `X-Forwarded-For` từ `PEMA_TRUSTED_PROXIES`, cookie phiên `Secure`; FE đọc địa chỉ API lúc chạy (`PEMA_API_INTERNAL_URL`).
15. **Màn Nhân viên** (`/admin/users`, vòng H4, 2026-10-02): chủ và quản lý xem danh sách nhân viên (`admin.users.read`); chỉ chủ thêm, sửa họ tên và vai trò, khóa hoặc mở khóa, đặt lại mật khẩu (`admin.users`). Không xóa hẳn nhân viên. Chủ không tự khóa hay tự đổi vai trò của mình, phòng khám luôn còn một chủ đang hoạt động, khóa hoặc đổi vai trò thì người đó bị đăng xuất khỏi mọi thiết bị. Chưa quyết: owner có được khóa hay đặt lại mật khẩu owner khác không (hiện được); có mở quyền xem danh sách cho CSKH và lễ tân (để ô "Phụ trách" dùng danh sách) không (chưa mở).
16. **Một hệ thống một phòng khám** (single-tenant, nhánh `feat/single-tenant`, migration `st_0009_single_tenant`). Lý do: yêu cầu bảo mật cao của phòng khám, bệnh viện, ngân hàng: dữ liệu của hai tổ chức không chung CSDL, Redis, khóa hay tiến trình, thay vì tin vào một chốt phần mềm (RLS). Giữ cột `clinic_id` làm mã cài đặt cố định; `clinic.clinic` đúng một dòng (CSDL bảo đảm), tạo bởi migration từ `PEMA_CLINIC_NAME` (mặc định `Pema Clinic`, slug cố định `clinic`, mã từ `PEMA_CLINIC_ID` nếu đặt); gỡ RLS và các hàm chọn phòng khám; đăng nhập chỉ email và mật khẩu; đường webhook Zalo không có đoạn phòng khám; vẫn nhiều tài khoản Zalo trong một phòng khám; giữ role `be_app`/`agent_worker` và view `clinic_agent`. Hai nhánh song song (đa phòng khám và một phòng khám) được giữ; tính năng về sau làm trên single-tenant trước (ARCH-AI01 mục 14). Hệ quả bảo mật: SECURITY-REVIEW-AI01 mục 7.

## 8. Điều chưa kiểm chứng

Tài liệu không coi các mục dưới đây là đã xong. Mỗi mục ghi rõ cái gì đã có bằng chứng.

| Hạng mục | Đã có | Chưa có |
|---|---|---|
| Zalo thật | Test với client giả (Bot API) và cầu nối giả cho `zca-js`; kịch bản vòng khép kín trên Postgres + Redis tạm | Chưa chạy với bot Zalo thật (polling, webhook, `setWebhook`), chưa quét QR với tài khoản thật, chưa đo giới hạn của Zalo |
| LLM thật | Vòng lặp chạy với mô hình giả có kịch bản; bộ eval có hướng dẫn chạy | Chưa có lần chạy eval với mô hình thật (D1 ghi rõ); chưa đo chất lượng gọi tool của Qwen3-8B với engine này |
| Ollama | F đã nạp Qwen3-8B Q5_K_M và bge-m3 trong container Docker trên RTX 3060 12 GB (Windows) và đo VRAM | Chưa chạy Ollama cài trực tiếp trên Ubuntu; chưa chạy engine + eval qua Ollama; Q6_K chưa đo; llama-server chỉ là roadmap |
| Reverse proxy | Dựng thật stack `postgres redis migrate api frontend caddy` ở chế độ `internal` (Docker Desktop trên Windows): đăng nhập thật qua Caddy bằng curl, refresh, chủ đặt lại mật khẩu nhân viên và phiên của người đó bị thu hồi | Chưa thử Let's Encrypt thật (chế độ `auto`), chưa có tên miền thật, chưa chạy trên Ubuntu có IP công cộng; chưa thử trình duyệt thật với gốc CA nội bộ |
| Ubuntu thật | Docker, Postgres + pgvector, Redis, role, migration, sao lưu bản không mã hóa đã chạy (Docker Desktop trên Windows) | Driver NVIDIA, NVIDIA Container Toolkit, Tailscale/WireGuard, ufw, NUT/UPS, timer systemd chưa chạy trên máy Ubuntu thật |
| Sao lưu mã hóa | Script, đường không mã hóa | Mã hóa age/gpg chưa chạy thử; diễn tập khôi phục có mã hóa chưa làm |
| FE | Chạy với backend mock (`pnpm dev:mock`); test hợp đồng mock với OpenAPI; script chụp 5 viewport | Chưa kiểm trên thiết bị thật; chưa có bằng chứng chạy FE nối API thật trong một phiên thủ công |
| Hiệu năng | Thiết kế api 1 worker, worker tách riêng | Chưa đo tải, độ trễ p95, hay số cuộc trò chuyện đồng thời |
| Cờ đỏ, PII | Test với dữ liệu hư cấu, có/không dấu, sai dấu, kéo dài chữ | Chưa kiểm với tin thật của bệnh nhân; danh sách và chữ chưa được bác sĩ duyệt |

Các test cần dịch vụ ngoài (Postgres + pgvector, Redis) được đánh dấu `db` / `redis` và bị bỏ qua khi thiếu `PEMA_TEST_DATABASE_URL` / `PEMA_TEST_REDIS_URL`. Một lần `make test` không đặt biến đó **không** chứng minh phần DB, role/grant và vòng khép kín. Tài liệu này không ghi số test đã chạy; số liệu phải lấy từ lần chạy lại tại thời điểm cần.

## 9. Việc mở cần chủ phòng khám hoặc bác sĩ quyết định

Mã đã giữ một giá trị mặc định cho từng mục để chạy được; giá trị đó không phải quyết định sản phẩm.

1. **Cờ đỏ và câu chữ.** Bốn nhóm bắt buộc (chảy máu, sốt, mưng mủ, khó thở) và hai nhóm *tạm thời* gói P tự thêm (`severe_allergy`, `vascular_vision`) cần bác sĩ xác nhận, bổ sung hoặc bỏ. Danh sách là dữ liệu (`RED_FLAG_RULES`). Câu nháp giữ chỗ gửi bệnh nhân (`RED_FLAG_HOLDING_DRAFT`, `MEDIA_FLAG_HOLDING_DRAFT`) là chữ hư cấu, bác sĩ viết lại. Cân nhắc dương tính giả (bác sĩ xem thừa) và âm tính giả (bỏ sót).
2. **Ma trận phân quyền.** Mã theo ARCH-PB01 và các lựa chọn của B1: lễ tân không đọc Patient 360 và hội thoại; quản lý không duyệt mục lâm sàng; CSKH không thấy mục lâm sàng; chỉ bác sĩ và chủ phòng khám ký duyệt tài liệu KB (quản lý được sửa KB nhưng không ký). Chủ phòng khám xác nhận từng ô. Thu ngân không có vai trò trong API này. Vai trò bệnh nhân rỗng.
3. **Persona hỏi SĐT hoặc mã xác minh.** Cách agent mời bệnh nhân cung cấp số điện thoại đã đăng ký hoặc mã lễ tân phát (câu chữ, số lần hỏi). Số điện thoại chỉ tạo liên kết `pending`; nhân viên xác nhận. Mã lễ tân hết hạn sau 30 phút; sai quá 5 lần mỗi giờ thì khóa.
4. **Trấn an tự động.** Khi gặp cờ đỏ hôm nay **không có tin nào tự đến bệnh nhân**: chỉ có `triage_alert` cho bác sĩ và một nháp để người gửi. Có nên gửi ngay một câu trấn an cố định không cần duyệt không?
5. **Nhắc tự động trước khi duyệt mẫu.** Luật CRM mặc định chỉ tạo việc nhân viên (`staff_task`). `auto_reminder` yêu cầu mẫu đã được bác sĩ duyệt. Có cho nhắc tự động trong lúc mẫu chưa được duyệt không (mã hiện từ chối).
6. **Trần tin chủ động 10 mỗi ngày.** Số này (mỗi bệnh nhân mỗi account mỗi ngày trong `patient_channel`) và cửa sổ giờ gửi, khoảng cách giữa tin là mặc định kế thừa từ zalo-agent, chưa đối chiếu với thực tế phòng khám hay mức Zalo chịu được.
7. **Thời hạn lưu dữ liệu theo Nghị định 13/2023.** Lịch sử hội thoại, trace, ảnh, bản sao lưu. Mã có khóa chỉnh (`HISTORY_MAX_MESSAGES_PER_THREAD` mặc định 500, `AGENT_TRACE_RETENTION_DAYS` 7, `MEDIA_RETENTION_DAYS` 7, bản sao lưu 14 ngày) và, từ vòng H, tác vụ `pema.retention` với một biến ngày cho mỗi nhóm (`PEMA_RETENTION_*`, 0 = giữ mãi; mặc định 0 cho lịch sử, bộ nhớ, tin nhắn, usage). **Các con số thật do chủ phòng khám quyết định**; mã chỉ cho đời ngắn với dữ liệu thuần kỹ thuật (trace 7, ảnh 7, `job_runs` 30, phiên hết hạn 1, mã liên kết 7, lần liên kết sai 30 ngày). **Chưa có quy tắc xóa** cho `review_item` đã quyết, `display_name` và `contacts`, `crm_activity`, tóm tắt hội thoại.
8. **Vị trí server.** Tại phòng khám hay cloud Việt Nam; sao lưu ngoài phòng khám; UPS. Hướng dẫn Ubuntu viết cho cả hai.
9. **Nơi lưu tệp** (ảnh khách gửi, tệp KB tải lên, tài liệu sinh ra): hiện là volume cục bộ `pema-data` (`PEMA_DATA_DIR`); object storage chưa làm.
10. **Webhook HTTPS.** Chế độ webhook cần địa chỉ HTTPS công khai Zalo gọi tới được (Tailscale Funnel, reverse proxy, hay cloud). Profile `proxy` (Caddy, chế độ `auto`) cho đường `/api/v1/webhooks/*` đi qua, trừ webhook cầu nối bị chặn từ ngoài. Mặc định đang là polling để khỏi cần địa chỉ công khai.
11. **MCP cho bệnh nhân.** `patient_channel` chặn mọi tool MCP. Có cho một MCP nào đó (ví dụ tra lịch) cho kênh bệnh nhân không, và ai duyệt.

12. **Client gọi API theo kiểu cũ (single-tenant).** Ứng dụng bệnh nhân (web, KMP) và mọi client hay script khác gọi đăng nhập có trường phòng khám (slug) hoặc đường webhook `/api/v1/webhooks/zalo-bot/<clinic>/<account>` / `.../zalo-bridge/<clinic>/<account>` phải đổi theo hợp đồng mới (đăng nhập chỉ email và mật khẩu; webhook không có đoạn phòng khám). Chưa kiểm client nào ngoài `pema-agent/`; việc rà từng client là của chủ sản phẩm. Webhook đã đăng ký ở Zalo bằng đường cũ phải đăng ký lại.
13. **Phòng khám thứ hai.** Mỗi phòng khám là một bản cài riêng (`infra/README.md`, "One system, one clinic"); chủ sản phẩm quyết định cách vận hành nhiều bản cài (ai giữ khóa, ai sao lưu, cập nhật phiên bản đồng loạt thế nào). Không có công cụ quản lý nhiều bản cài trong repo này.

Việc mở khác (kỹ thuật, chưa cần chủ phòng khám) ở ARCH-AI01 mục 13: chọn account khi nhiều account cùng loại, liên kết vai trò bệnh nhân với hồ sơ, và các sửa tài liệu hạ tầng còn lại.
