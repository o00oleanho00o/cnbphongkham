# Pema Agent — Software Specification AI01

Đọc sau [SCOPE-AI01](SCOPE-AI01.md). Trạng thái: mô tả hành vi của mã trên nhánh `feat/ai-agent-backend` (commit `1ce6cca`), ngày 2026-10-02. Cột "Bằng chứng" chỉ tên file test hoặc mã có thật; cột "Mức kiểm chứng" nói thẳng test chạy với đồ giả hay đã chạy với hệ thống thật (xem SCOPE-AI01 mục 8). Không có tiêu chí nào dưới đây đã được kiểm với Zalo thật, mô hình thật hay thiết bị thật.

Quy ước mức kiểm chứng: **Giả** = pytest/vitest với đồ giả (mô hình giả có kịch bản, client Bot API giả, cầu nối giả). **Giả + DB** = thêm Postgres + pgvector và Redis tạm (đánh dấu `db`, `redis`; bị bỏ qua khi thiếu `PEMA_TEST_DATABASE_URL` / `PEMA_TEST_REDIS_URL`). **Tay** = làm bằng tay một lần, ghi trong tài liệu hạ tầng. **Chưa** = chưa có.

## 1. Vai trò và use case

| ID | Use case | Tác nhân | Kết quả |
|---|---|---|---|
| UC-AI01 | Bệnh nhân nhắn hỏi chăm sóc, agent soạn nháp | Bệnh nhân, agent | Một `review_item` loại `reply_draft` trong hàng chờ; chưa có tin nào đến bệnh nhân |
| UC-AI02 | Nhân viên duyệt (có thể sửa) rồi gửi | CSKH, bác sĩ | Văn bản đã duyệt được xếp hàng và gửi qua kênh; mục được đánh dấu đã gửi |
| UC-AI03 | Bệnh nhân nhắn dấu hiệu nguy hiểm | Bệnh nhân | Không gọi mô hình; `triage_alert` đến bác sĩ; không tin nào tự gửi |
| UC-AI04 | Bệnh nhân gửi ảnh hoặc tệp | Bệnh nhân | `media_flag` ở Inbox; agent không xử lý, không trả lời |
| UC-AI05 | Liên kết `zalo_uid` với hồ sơ | Bệnh nhân, lễ tân, CSKH | Liên kết `verified` (mã lễ tân) hoặc `pending` rồi nhân viên xác nhận (số điện thoại) |
| UC-AI06 | Agent tra bối cảnh chăm sóc và đề xuất lịch | Agent, nhân viên | Kết quả không mang tên; đề xuất lịch thành `review_item`, nhân viên xác nhận thì lịch được đặt |
| UC-AI07 | Luật CRM sinh việc và job nhắc | Hệ thống | Việc cho nhân viên; job `message` từ mẫu đã duyệt hoặc nháp chờ duyệt |
| UC-AI08 | Nhân viên cấu hình AI | Chủ, quản lý | Account/QR, agent/persona, model, tool, KB, lịch, MCP, chính sách, công tắc khẩn |
| UC-AI09 | Vận hành hằng ngày | CSKH, bác sĩ, lễ tân | Việc hôm nay, Inbox, hàng duyệt, hồ sơ, tin mẫu |
| UC-AI10 | Dừng khẩn cấp gửi tin | Chủ, quản lý | Kill switch theo kênh; cầu nối có thêm lệnh dòng lệnh |

## 2. Hành vi theo hồ sơ chính sách (yêu cầu)

Nguồn của bảng là `DEFAULT_PROFILES`; `ClinicPolicyHooks` (`pema/policy/hooks.py`) thực thi bằng tám hook `before_llm`, `after_llm`, `filter_tool_keys`, `allow_memory_write`, `on_outbound`, `check_job`, `proactive_cap`, `verify_identity`. Nơi gọi từng hook ở CONTRACTS-AI01 mục 3.

Nguyên tắc chung khi chính sách không quyết định được (DB lỗi, action lỗi): **đóng** (fail closed). Cờ đỏ vẫn là chuyển người dù không tạo được `review_item` (lý do ghi là lỗi leo thang, người gọi thử lại); job không kiểm được mẫu thì bị từ chối.

### 2.1 Thứ tự một lượt hội thoại (chuẩn tắc)

1. `before_llm` trên cả lô tin. `HAND_OFF` dừng tại đây: **mô hình không được gọi**.
2. Mô hình chỉ nhận văn bản **đã che PII**.
3. `after_llm` khôi phục **chỉ tên** trong câu trả lời.
4. `on_outbound`: `SEND` (staff_assistant) hoặc `HOLD_FOR_REVIEW` (patient_channel; người gọi tạo `review_item`) hoặc `DROP`.

`pema/policy/turn_guard.py` viết đúng thứ tự này thành một hàm tham chiếu để test chứng minh tính chất quan trọng nhất: tin có cờ đỏ không bao giờ tới mô hình.

### 2.2 Cờ đỏ

Bốn nhóm bắt buộc: `bleeding`, `fever`, `pus`, `dyspnea`. Hai nhóm tạm thời cần bác sĩ xác nhận: `severe_allergy`, `vascular_vision`. Thứ tự báo: khó thở, dị ứng nặng, chảy máu, mạch máu/thị lực, sốt, mưng mủ. So khớp chạy trên văn bản đã chuẩn hóa: chữ thường, bỏ dấu, bỏ chữ kéo dài ("chayyy mau") và dấu phân cách chen giữa chữ ("ch.ảy"). Quy tắc nghiêng về an toàn:

- Mơ hồ thì gắn cờ, **trừ** vài từ thường ngày nghĩa khác ("sốt ruột", "mũ", "sót", "màu cam"); vệt này loại bằng cách nhìn dấu bệnh nhân thật sự gõ.
- Phủ định ("không sốt", "hết sốt", "không bị chảy máu") chỉ loại bỏ khi từ phủ định đứng ngay trước từ khóa; "chưa hết sốt", "không hết sốt" vẫn là cờ; "không thở được" không bao giờ bị phủ định. Hit bị loại vẫn trả về ở `suppressed` để log hoặc eval xem được.
- Danh sách luật là dữ liệu (`RED_FLAG_RULES`) để bác sĩ sửa mà không đụng logic.

Khi có cờ: tạo `review_item` loại `triage_alert` (`requires_doctor`), kèm `media_flag` nếu tin có ảnh, trả `HAND_OFF`. Mục chỉ mang mã và id, không chép lời bệnh nhân (lời đã ở Inbox).

### 2.3 Che PII

Che trước mọi lời gọi mô hình trong `patient_channel`: số điện thoại (có `+84`/`84`/`0084`, mọi dấu ngăn cách, số đánh vần bằng chữ), CCCD 12 số, CMND 9 số cạnh từ khóa, email (kể cả "abc at gmail dot com"), địa chỉ cụ thể (số nhà + đường/hẻm, tòa/tầng/phòng), ngày sinh cạnh từ khóa, và tên (tên kênh của người gửi, tên bệnh nhân đã xác minh, "tên là X"). Tên bệnh nhân đã xác minh thành `[KH_<mã>]`, người khác thành `[NGUOI_n]`.

Khôi phục chỉ tên và chỉ những tên phiên này đã tạo; SĐT, CCCD, email, địa chỉ, ngày sinh **không bao giờ** được khôi phục. Chỗ giữ mà mô hình tự bịa, hoặc không khôi phục được, thành `[đã ẩn]` để người duyệt thấy lỗ hổng chứ không thấy rò rỉ. Giới hạn nói thẳng: tên viết thường không giới thiệu ("em hoa"), số điện thoại tách ba tin, địa chỉ không có số nhà ("nhà em gần chợ X") **không** được che; tấm lưới an toàn cho các ca đó là kiểm cờ đỏ và hàng duyệt.

### 2.4 Xác minh danh tính

Trong `patient_channel`, agent không được nêu tên, lịch hẹn hay thuốc cho tới khi `zalo_uid` liên kết với hồ sơ đã xác minh.

- **Số điện thoại**: chuẩn hóa rồi băm SHA-256 ở tiến trình worker; chỉ **băm** đi vào DB. Khớp đúng một bệnh nhân thì liên kết `pending` (không phải xác minh, vì ai biết số cũng nhận được); nhân viên xác nhận (`POST /admin/policy/identity/confirm`, quyền `admin.policy`). Khớp nhiều bệnh nhân (số dùng chung trong gia đình) là `ambiguous`, chuyển người.
- **Mã lễ tân**: lễ tân cấp mã dùng một lần cho **một** bệnh nhân (8 ký tự từ bảng 31 ký tự bỏ `0 O 1 I L`), đưa tại phòng khám; bệnh nhân gõ vào chat; hợp lệ thì `verified` ngay (người cấp mã là người xác minh), mã hết hiệu lực. Mã hết hạn sau 30 phút; chỉ băm của mã được lưu.
- Cả hai đường đếm lần thử sai theo (kênh, người dùng) trong DB và trả `rate_limited` sau 5 lần sai trong một giờ.
- Chưa xác minh: câu hệ thống thêm cho mô hình dặn "hỏi cách xác minh, đừng đoán"; tool phòng khám trả lỗi có đánh dấu `NOT_VERIFIED`; một `identity_check` được mở cho nhân viên.

### 2.5 Hàng chờ duyệt

Các loại `review_item`: `reply_draft` (trả lời tin bệnh nhân), `followup_draft` (tin từ job theo lịch hoặc luật CRM cần người), `triage_alert` (cờ đỏ), `media_flag` (ảnh/tệp), `identity_check` (liên kết chưa xác minh). Nguồn: `agent_turn`, `scheduled_agent`, `crm_rule`, `policy`.

- Tạo mục là idempotent theo `job_id` dẫn xuất từ id ổn định (account, thread, id tin), không từ đồng hồ: lượt chạy lại tìm mục cũ thay vì mở mục thứ hai.
- Mục `requires_doctor` hoặc `triage_alert` chỉ **chủ hoặc bác sĩ** quyết định (`review.decide_clinical`); CSKH không duyệt và không thấy chúng. Người còn lại duyệt phần không lâm sàng (`review.decide`).
- Quyết định là cuối cùng: đã duyệt, từ chối, hết hạn thì không quyết lại; `version` chặn hai người cùng quyết; `Idempotency-Key` lặp lại trả kết quả cũ, không gửi hai lần. Mục `escalated` vẫn được bác sĩ duyệt hoặc từ chối.
- Duyệt kèm gửi: văn bản đã duyệt được lưu ở trạng thái `queued` **trong cùng giao dịch** với quyết định, rồi giao cho kênh (`deliver_queued_message`), sau đó dòng tin được đánh dấu đã gửi hoặc bị từ chối. Tin phát từ job (`scheduled_agent`, `crm_rule`) đi đường **chủ động** (trần, cửa sổ giờ, kill switch áp dụng); trả lời tin bệnh nhân thì không.
- Mục mang đề xuất lịch (`payload.proposal == "appointment"`) đặt lịch trong cùng giao dịch qua **cùng validator với giao diện**; xung đột thì mục vẫn `pending` để nhân viên chọn giờ khác.

### 2.6 Tool của agent

15 tool gốc (`BUILTIN_TOOL_KEYS`) và bốn tool phòng khám. `patient_channel` tắt `send_file`, `create_word_document`, `create_excel_file`, `create_image`, `tai_video`, `read_image`, `web_search`, `web_fetch`, toàn bộ tool MCP, và ẩn `save_memory`. Bốn tool phòng khám chỉ có khi `ToolDeps.clinic_actions` được đưa vào và hồ sơ đòi xác minh:

- `patient.get_care_context`: bối cảnh chăm sóc (số buổi còn lại, lịch sắp tới, đồng ý), **không** tên, SĐT hay ghi chú.
- `appointment.book`: chỉ **đề xuất** lịch; nhân viên xác nhận.
- `review_item.create`: **soạn nháp** một tin nhắn (`followup_draft`) cho nhân viên duyệt; tin không đi đâu cho đến khi có người duyệt. Chỉ nhận nội dung nháp (không nhận bệnh nhân, loại, mức rủi ro hay cờ đỏ). Câu trả lời của chính lượt đó đã tự được giữ để duyệt, nên tool này dành cho tin KHÔNG phải câu trả lời của lượt (tin hỏi thăm của job agent theo lịch, đề xuất chăm sóc).
- `escalation.create`: tạo `triage_alert` cho bác sĩ.

Bệnh nhân **không bao giờ** là tham số của tool: tool lấy bệnh nhân từ danh tính đã xác minh của lượt, để mô hình bị dụ cũng không đọc được hồ sơ người khác. Khóa idempotency của lần ghi dẫn xuất từ (phòng khám, account, thread, id tin gây ra lượt). Cả bốn khóa của `CLINIC_TOOL_KEYS` đều là tool đã đăng ký.

### 2.7 Bộ lập lịch và tin chủ động

- Loại job: `message` (nội dung từ mẫu `clinic.message_template` đã duyệt; `payload` mang khóa mẫu) và `agent` (một lượt cô lập: không lịch sử, không bộ nhớ).
- `patient_channel`: `check_job` chỉ cho `message` từ mẫu đã duyệt; job `agent` bị hạ thành nháp; tiếp thị bị từ chối nếu bệnh nhân `marketing_opt_out`; sinh nhật bị từ chối. Nội dung điền chỗ giữ (placeholder) trong mẫu chỉ khi danh tính đã xác minh.
- **Trần tin chủ động**: mặc định 10 mỗi ngày (`SCHEDULER_MAX_PROACTIVE_PER_DAY`), khóa theo `account:thread` (staff_assistant) hoặc `patient:account` (patient_channel). Số hiệu lực là số nhỏ hơn giữa hook và `channel_setting.daily_cap`; không bao giờ không có trần. Có hai chốt: đọc sớm trước khi chạy agent (tránh tốn LLM, không giữ chỗ) và `reserve_proactive_slot` nguyên tử (một upsert có điều kiện) ngay lúc gửi thật; sổ đếm bền qua khởi động lại, giữ 3 ngày.
- Trước **mọi** tin chủ động: account đang chạy, thread còn hiệu lực và `bot_enabled`, kênh không bị tắt, **kill switch không bật**, trong cửa sổ giờ gửi (`send_window_start..end`, múi giờ bot, có thể qua nửa đêm). Dòng `channel_setting` đọc lại ở mỗi lần gửi, không cache, nên bật kill switch dừng tin kế tiếp ở mọi tiến trình. Kênh chưa có dòng cấu hình thì không bị giới hạn toàn phòng khám (hành vi gốc).
- Hàng đợi gửi chủ động có khoảng cách `SCHEDULER_SEND_GAP_MS` (mặc định 20 giây). Tài khoản cá nhân thêm khoảng ngẫu nhiên giữa hai tin (`min_gap_seconds..max_gap_seconds`) và có thể yêu cầu người nhận trong thread riêng là bạn bè (danh sách lấy từ cầu nối, đệm 10 phút; cầu nối không với tới thì từ chối).
- Bất biến gốc "chưa gửi thì chưa chạy" được giữ ở bộ lập lịch (dịch từ `src/scheduler`).

### 2.8 Luật CRM

Mười luật của `crm-data.js` (`d1`, `d3`, `d7`, `due`, `overdue`, `no_show`, `abandoned`, `dormant90`, `dormant180`, `birthday`), mặc định `send_mode = staff_task`. Việc theo khóa = luật + bệnh nhân + sự kiện nguồn, nên chạy lại không sinh trùng. Job mang `dedupe_key` = khóa việc; job tạo **sau** việc nên lỗi giữa chừng được lần chạy sau sửa. Luật sinh nhật luôn là `staff_task` (CHECK trong DB và `validate_send_mode`). Luật tiếp thị (`dormant90`, `dormant180`, `birthday`) không tạo job cho bệnh nhân `marketing_opt_out`. Runner chạy trong tiến trình API mỗi `PEMA_CRM_RUNNER_INTERVAL_SECONDS` (mặc định 900; 0 là tắt, chạy tay). Khi bộ lập lịch từ chối (ví dụ `check_job`), việc của nhân viên vẫn ở lại.

## 3. Bảng tiêu chí nghiệm thu

| ID | Tiêu chí | Bằng chứng | Mức |
|---|---|---|---|
| AC-AI01-01 | `patient_channel`: tin ra khách thành `reply_draft`; nhân viên duyệt qua API rồi mới gửi qua kênh; trước đó kênh không gửi gì | `tests/integration/test_loop_patient_channel.py`; `tests/policy/test_hooks_patient_channel.py` | Giả + DB |
| AC-AI01-02 | `staff_assistant`: tin Zalo đến engine, gọi tool, trả lời gửi thẳng; mỗi hook trả như `PermissivePolicyHooks` | `tests/integration/test_loop_staff_assistant.py`; `tests/policy/test_hooks_staff_assistant.py` | Giả + DB |
| AC-AI01-03 | Cờ đỏ (có/không dấu, sai dấu, kéo dài chữ): mô hình giả **không bị gọi**, có `triage_alert`, không tin nào gửi | `tests/integration/test_loop_red_flags_and_media.py` (tham số hóa); `tests/policy/test_redflags.py`; `tests/policy/test_clinic_eval_cases.py` | Giả + DB |
| AC-AI01-04 | Ảnh khách gửi: `media_flag`, không phân tích, không gửi gì | `tests/integration/test_loop_red_flags_and_media.py` | Giả + DB |
| AC-AI01-05 | PII che trước mô hình; chỉ khôi phục tên; chỗ giữ lạ thành `[đã ẩn]` | `tests/policy/test_pii.py`, `tests/policy/test_text_normalize.py` | Giả |
| AC-AI01-06 | Xác minh: mã một lần, SĐT băm tạo `pending`, giới hạn 5 lần sai mỗi giờ; chưa xác minh thì có lời nhắc xác minh và nháp vào hàng duyệt | `tests/policy/test_identity.py`, `test_identity_sql.py`; `tests/integration/test_loop_patient_channel.py` | Giả + DB |
| AC-AI01-07 | Tool phòng khám: đã xác minh thì có bối cảnh, kết quả không có tên; chưa xác minh thì lỗi có đánh dấu; đặt lịch là đề xuất, nhân viên xác nhận mới đặt; staff_assistant không nhận tool | `tests/integration/test_loop_clinic_tools.py`; `tests/clinic/test_agent_facing.py` | Giả + DB |
| AC-AI01-08 | Duyệt: chỉ bác sĩ/chủ duyệt mục lâm sàng; idempotent; mọi quyết định có audit | `tests/clinic/test_api_conversations_reviews.py`, `test_rbac_matrix.py`, `test_rbac_endpoints.py` | Giả + DB |
| AC-AI01-09 | Mọi thay đổi có audit; `agent_worker` không có quyền trên `clinic.*`; `clinic.clinic` đúng một dòng (nhánh single-tenant: bỏ ý "RLS cách ly hai phòng khám", `test_rls_isolation.py` bị xóa) | `tests/clinic/test_audit_every_mutation.py`; `tests/test_database.py`; `tests/policy/test_identity_sql.py` | Giả + DB |
| AC-AI01-10 | Engine luật Python cho cùng kết quả với engine JS gốc (đồng hồ 2026-09-20, P025..P032 và mười ca mobile) | `tests/clinic/crm_rules/test_crm_equivalence.py` (JSON đã commit, không cần node) | Giả |
| AC-AI01-11 | Luật CRM → job → tin chủ động theo hồ sơ; sinh nhật không tự gửi; opt-out chặn | `tests/integration/test_loop_crm_scheduler.py`; `tests/clinic/crm_rules/test_crm_runner.py` | Giả + DB |
| AC-AI01-12 | Trần, kill switch, cửa sổ giờ, trần theo (bệnh nhân, account) | `tests/scheduler/test_proactive_send_guard.py`, `test_proactive_send_counter_store.py`, `test_scheduler_policy.py`; `tests/channels/zalo_personal/test_proactive_gate.py` | Giả (+ DB) |
| AC-AI01-13 | Mỗi họ route admin: ẩn danh 401, vai trò thiếu quyền 403, đủ quyền 200 | `tests/integration/test_admin_access_matrix.py` | Giả + DB |
| AC-AI01-14 | Kênh Bot API và cá nhân: parser, webhook, trùng `update_id`, router, QR, kết nối lại | `tests/channels/zalo_bot/*`, `tests/channels/zalo_personal/*`; `backend/bridges/zalo-personal/src/*.test.ts` | Giả |
| AC-AI01-15 | OpenAPI committed khớp mã; PORT-MAP phủ mọi file `src/` của bản tham chiếu | `tests/test_openapi_skeleton.py`; `tests/test_port_map.py` (cần bản clone ngoài repo, nếu không thì bị bỏ qua) | Giả |
| AC-AI01-16 | FE chạy với mock; mock phục vụ đúng các operation của hợp đồng | `frontend/mock/contract.test.ts`; `pnpm test`; `pnpm shots` (5 viewport, lỗi nếu tràn ngang) | Giả; thiết bị thật **Chưa** |
| AC-AI01-17 | Compose hợp lệ với mọi profile; migration + role chạy trên Postgres sạch | `make infra-config`; `make db-migrate` | Tay (Docker Desktop, Windows) |
| AC-AI01-18 | Zalo thật, mô hình thật, Ollama trên Ubuntu, sao lưu mã hóa, FE trên thiết bị thật | không có | **Chưa** |

## 4. API

Tiền tố `/api/v1`. `openapi.json` đã commit liệt kê 176 đường dẫn, 224 thao tác (`make openapi` sinh lại; test fail khi file cũ). Nhóm: `auth`, `me`, `permissions`, `patients` (cùng `consents`, `sessions`, `plans`, `consult-notes`, `media`, `approved-orders`, `360`), `appointments`, `dashboard`, `resources` (`rooms`, `room-blocks`), `services`, `protocols`, `studio`, `orders`, `catalog`, `finance`, `guide`, `media`, `crm`, `conversations`, `review-items`, `webhooks` (không dành cho FE), và `admin/*` (accounts, agents, channels, contacts, friends, kb, logs, mcp, memories, model, policy, rules, schedules, templates, threads, tools, traces, usage). `/healthz` ngoài tiền tố.

- Phiên là cookie HttpOnly sau `POST /auth/login` (JWT, mật khẩu argon2). Thiếu phiên: 401; thiếu quyền: 403; **deny by default**.
- Lỗi theo `ErrorResponse` với `ErrorCode` ổn định; thông điệp tiếng Việt, không chứa PII.
- Lần ghi nhận `Idempotency-Key` phát lại kết quả đầu cho cùng khóa.
- Thời gian ISO 8601 có `+07:00`; chuỗi thời gian không múi giờ bị từ chối.

## 5. Phân quyền

Tập quyền phẳng theo vai trò là **trần**; các luật hẹp hơn (bác sĩ chỉ hồ sơ mình phụ trách hoặc có lịch; bác sĩ chỉ sửa lịch của mình; CSKH không làm lâm sàng) do `pema.clinic.actions` kiểm tiếp. `owner` có mọi quyền của người, trừ `agent.submit` (thuộc tác nhân agent).

| Quyền (rút gọn) | Chủ | Quản lý | Bác sĩ | CSKH | Lễ tân |
|---|:-:|:-:|:-:|:-:|:-:|
| Hồ sơ bệnh nhân (đọc) | ✓ | ✓ | ✓ (giới hạn phụ trách) | ✓ | ✓ (danh tính, lịch) |
| Patient 360, hội thoại | ✓ | ✓ | ✓ | ✓ | ✗ |
| Sửa lịch, check-in | ✓ | ✓ | giới hạn lịch của mình | ✗ | ✓ |
| Ghi buổi điều trị (session) | ✓ | ✗ | ✓ | ✗ | ✗ |
| Duyệt mục thường | ✓ | ✓ | ✓ | ✓ | ✗ |
| Duyệt mục lâm sàng, cờ đỏ | ✓ | ✗ | ✓ | ✗ | ✗ |
| Việc CSKH (xem, xử lý) | ✓ | ✓ | giới hạn bệnh nhân mình | ✓ | ✗ |
| Quản trị KB (sửa) | ✓ | ✓ | ✓ | ✗ | ✗ |
| Ký duyệt tài liệu KB cho `patient_channel` | ✓ | ✗ | ✓ | ✗ | ✗ |
| Quản trị AI (account, agent, model, tool, lịch, MCP, chính sách, kill switch, luật, log, usage) | ✓ | ✓ | ✗ | ✗ | ✗ |
| Cấp mã xác minh | ✓ | ✓ | ✗ | ✓ | ✓ |
| Kế hoạch, buổi điều trị, bản nháp tư vấn (ghi) | ✓ | ✗ | ✓ | ✗ | ✗ |
| Ảnh trước/sau (tải lên, xem; cần đồng ý ảnh còn hiệu lực) | ✓ | ✗ | ✓ (giới hạn phụ trách) | ✓ | ✗ |
| Lên đơn thuốc/phiếu tư vấn nháp, xem danh mục sản phẩm | ✓ | ✓ | ✓ | ✗ | ✓ |
| Duyệt đơn (ký) | ✓ | ✗ | ✓ (đơn của mình) | ✗ | ✗ |
| Thu tiền, lập hóa đơn từ đơn | ✓ | ✓ | ✗ | ✗ | ✓ |
| Tài chính: tổng quan và bảng tiền thủ thuật của cả phòng khám | ✓ | ✓ | ✗ | ✗ | ✗ |
| Tài chính: chỉ các dòng mình thực hiện (Doanh số của tôi) | ✓ | ✗ | ✓ | ✗ | ✗ |
| Ghi, duyệt, hủy lượt thủ thuật; chốt tháng; xác nhận đã chi | ✓ | ✓ | ✗ | ✗ | ✗ |
| Thông báo thanh toán của chủ | ✓ | ✗ | ✗ | ✗ | ✗ |
| Dịch vụ, phòng, khóa phòng, phác đồ (sửa); danh mục sản phẩm chỉ nạp bằng CLI `pema catalog import`, không qua route | ✓ | ✓ | ✗ | ✗ | ✗ |

Vai trò bệnh nhân: không có quyền staff nào. Cột "Thu ngân" và "Kế toán" của ARCH-PB01 chưa có vai trò riêng: lễ tân thu tiền, quản lý giữ phần kế toán (SCOPE-AI01 mục 9). Các hàng về buổi điều trị, ảnh, đơn, tài chính, dịch vụ do gói U thêm; `tests/clinic/test_u8_security_pass.py` kiểm từng route đúng ma trận (403 chính xác khi vai trò không có quyền). Bảng trên là **bản tóm tắt**; nguồn thật là `pema/clinic/rbac/matrix.py`. Chủ phòng khám cần xác nhận từng ô (SCOPE-AI01 mục 9, việc 2).

## 6. Cấu hình

- 72 tham số chỉnh (`tuning_specs.py`) giữ **tên gốc không tiền tố** của zalo-agent (ví dụ `HISTORY_CONTEXT_LIMIT`, `SCHEDULER_MAX_PROACTIVE_PER_DAY`); đọc qua `get_tuning`, giá trị trên dashboard (`agent.runtime_settings`) thắng biến môi trường. Biến nền tảng có tiền tố `PEMA_`.
- Mặc định đáng chú ý: gộp tin `MESSAGE_BATCH_DEBOUNCE_MS=2500`; lịch sử `HISTORY_MAX_MESSAGES_PER_THREAD=500`; trace và media giữ 7 ngày; `SCHEDULER_TICK_MS=30000`, `SCHEDULER_MAX_JOBS_PER_THREAD=20`, `SCHEDULER_SEND_GAP_MS=20000`.
- Bí mật (token bot, thông tin Zalo, khóa API, header MCP) mã hóa AES-256-GCM bằng `PEMA_SECRET_ENCRYPTION_KEY`; DTO không bao giờ mang bí mật (`has_bot_token`, `api_key_masked`). Mất khóa này thì dữ liệu mã hóa không đọc lại được; giữ bản sao ngoại tuyến.
- Nhật ký: không PII; logger tự che các khóa `text`, `content`, `sender_name`, `phone`, `token`, `headers` nhưng mã không dựa vào đó; lỗi đi qua bộ tuần tự hóa an toàn.

## 7. Yêu cầu phi chức năng

- Tin trả về cho bệnh nhân có độ trễ do người duyệt; không có mục tiêu độ trễ thời gian thực cho `patient_channel`. Không có số đo tải hay p95 (SCOPE-AI01 mục 8).
- Một lượt cho một thread tại một thời điểm (khóa Redis theo account và thread). Tin đến giữa lượt được gộp vào lượt đang chạy.
- Hàng đợi lượt chịu được khởi động lại (Redis AOF); lượt của worker chết được trả lại hàng đợi (`reclaim_expired`, mỗi 60 giây).
- Tài liệu và dữ liệu mẫu hư cấu; không `.env`, không DB trong git.
- FE: 390×844 không tràn ngang cấp tài liệu, nút chạm tối thiểu 44 px ở màn điện thoại, bảng cuộn bên trong thẻ.
- Chưa có: mục tiêu khả dụng, RPO dưới một ngày (sao lưu hằng đêm, RPO một ngày), giám sát/cảnh báo ngoài log.
