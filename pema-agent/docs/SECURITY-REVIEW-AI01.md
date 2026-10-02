# SECURITY-REVIEW-AI01: rà bảo mật và đối chiếu PORT-MAP (gói G, phần 2)

Ngày: 2026-10-02. Nhánh tích hợp `feat/ai-agent-backend` (commit gốc `1ce6cca`). Người rà: gói G (subagent). Phạm vi: toàn bộ `pema-agent/` (backend Python, bridge Node, FE, infra), đọc code thật. Mọi dữ liệu dùng trong thử nghiệm là hư cấu.

Mức độ: **Cao** (lộ dữ liệu bệnh nhân hoặc bỏ qua chốt an toàn lâm sàng), **Trung bình** (khai thác được nhưng cần điều kiện, hoặc làm yếu một lớp bảo vệ), **Thấp** (làm cứng thêm), **Thông tin** (đã kiểm, không có lỗi).
Trạng thái: **Đã sửa** (kèm test), **Mở** (việc kỹ thuật chưa làm), **Quyết định** (cần chủ phòng khám hoặc chủ sản phẩm chọn).

## 1. Tổng hợp

| Mức | Số phát hiện | Đã sửa | Mở | Quyết định | Chấp nhận |
|---|---:|---:|---:|---:|---:|
| Cao | 2 | 2 | 0 | 0 | 0 |
| Trung bình | 11 | 8 | 1 | 2 | 0 |
| Thấp | 17 | 6 | 8 | 1 | 2 |
| Thông tin (đã kiểm, sạch) | 14 | - | - | - | - |

Tổng 44 mục (SEC-01 đến SEC-44). Mười sáu mục đã sửa kèm test mới; mọi test backend xanh sau khi sửa (xem mục 6).

## 2. Bảng phát hiện

### 2.1 PII và dữ liệu y tế

| ID | Mức | Nơi | Mô tả và kịch bản | Trạng thái |
|---|---|---|---|---|
| SEC-01 | Cao | `pema/workers/main.py` (`summarize_thread`), `pema/conversation/thread_summarizer.py` (`build_summary_prompt`, `maybe_summarize_thread`) | Sau mỗi lượt, worker tóm tắt hội thoại cũ bằng một lời gọi LLM riêng. Prompt dựng từ `agent.history` thô: tên người gửi, SĐT, nội dung bệnh nhân, không qua mặt nạ. Docstring cũ ghi "caller phải truyền generator có che", nhưng `composition/runtime.py` truyền `ProviderTextGenerator` trần. Đây là đường tới LLM bỏ qua `patient_channel` mask (nguyên tắc 4 của PLAN) và bản tóm tắt lưu lại cũng chứa PII thô. | **Đã sửa**: `maybe_summarize_thread(prompt_filter=...)`; worker tính hồ sơ hiệu lực của account+agent, nếu `pii_mask=REQUIRED` thì chạy `mask_text` của chính sách trên cả prompt, không có mặt nạ hoặc mặt nạ lỗi thì KHÔNG gọi model. Test: `tests/conversation/test_thread_summarizer_masking.py` |
| SEC-02 | Cao | `pema/policy/redflags.py` (`detect_red_flags_in_batch`), `pema/policy/text_normalize.py` | Cờ đỏ bị bỏ lọt: (a) dấu hiệu tách hai tin của cùng lượt ("chảy" / "máu") vì dò từng tin riêng, trong khi mô hình đọc hai dòng liền nhau; (b) ký tự vô hình cạnh khoảng trắng ("chảy&#8203; máu"), chữ toàn chiều rộng, chữ in đậm toán học, khoảng trắng lạ (NBSP, ideographic) vì chuẩn hóa chỉ NFC; (c) "bớt chảy máu" bị coi là phủ định (bớt là còn); (d) tin tiếng Anh ("bleeding", "can't breathe") không có luật. Mỗi điểm là một lần bác sĩ không được báo. | **Đã sửa**: quét thêm văn bản ghép của cả lượt; NFKC từng ký tự, bỏ mọi ký tự `Cf`, khoảng trắng lạ thành dấu cách (giữ `source_index`); bỏ "bớt" khỏi từ phủ định; thêm bốn luật tiếng Anh không phủ định. Test thêm trong `tests/policy/test_redflags.py`. Không sửa: chữ lẫn Cyrillic/leetspeak ("ch4y m4u"), chữ cách ("c h ả y") |
| SEC-03 | Trung bình | `pema/policy/hooks.py` (`MEDIA_KINDS_TO_FLAG`), `pema/channels/zalo_personal/zalo_message_parser.py` | Tài khoản cá nhân: mọi tệp đính kèm không phải ảnh (giọng nói, video, tệp, vị trí) vào hệ thống với `kind=text`, chữ rỗng; kind `unsupported` của Bot API cũng không bị gắn cờ. Bệnh nhân gửi video vết thương hoặc ghi âm "khó thở" thì không chuyển người, agent trả lời một tin rỗng. | **Đã sửa**: `UNSUPPORTED` vào danh sách chuyển người; hook đọc thêm `raw["msgType"]` (voice, video, file, location, gif, doc, audio, photo). Test trong `tests/policy/test_hooks_patient_channel.py` |
| SEC-04 | Trung bình | `pema/shared/logger.py`, `pema/shared/safe_error_serializer.py` | (a) Bộ che khóa log thiếu nhiều tên (`caption`, `draft_text`, `prompt`, `reply`, `summary`, `query`, `*_token`...). (b) `serialize_error_safely` ghi `str(err)`: với `pydantic.ValidationError` chuỗi này trích `input_value` (lời bệnh nhân, SĐT) và nó còn nằm trong `stack`. | **Đã sửa**: thêm khóa và hậu tố (`_token`, `_secret`, `_text`, `_body`...; không dùng khớp chuỗi con để bộ đếm như `tokens_in` còn đọc được); ValidationError chỉ giữ loại lỗi và vị trí, `stack` không còn dòng thông báo. Tests: `test_logger.py`, `test_safe_error_serializer.py` |
| SEC-05 | Thấp | `pema/agent/tools/clinic_tools.py` (`_conversation_ref`) | Tool gọi `record_inbound_message` với tin ĐÃ che (`sender_name="[NGUOI_1]"`): hàm SQL upsert `channel_identity.display_name` nên tên thật bị ghi đè bằng mã giữ chỗ sau mỗi lần escalation. Hỏng dữ liệu, không lộ. | **Đã sửa**: chỉ truyền id, bỏ tên và chữ. Test trong `tests/agent/tools/test_clinic_tools.py` |
| SEC-06 | Thấp | `pema/conversation/agent_trace_store.py`, `summarize_step` | Trace (bảng DB, RLS, giữ 7 ngày, 500 ký tự mỗi trường) lưu đầu ra tool thô trong `patient_channel` (bộ lọc mặt nạ chỉ áp lên bản gửi cho mô hình). Không ra file hay log. | **Thời hạn trace cấu hình được** (vòng tích hợp H): tác vụ `pema.retention` xóa `agent.usage_steps` quá `PEMA_RETENTION_TRACE_DAYS` ngày (bỏ trống = khóa chỉnh `AGENT_TRACE_RETENTION_DAYS`, mặc định 7; 0 = giữ mãi), từng lô nhỏ, chạy ở worker. **Còn quyết định**: giữ nguyên hay tắt `AGENT_TRACE_ENABLED` cho hồ sơ `patient_channel`, và số ngày thật (chủ phòng khám, Nghị định 13) |
| SEC-07 | Thấp | `pema/policy/pii.py` (`MaskSession`) | Mã giữ chỗ tên (`[NGUOI_n]`) đánh số theo phiên trong RAM; bản tóm tắt lưu mã của phiên cũ, phiên mới có thể gán `[NGUOI_1]` cho người khác và `after_llm` khôi phục sai tên. Một thread là một bệnh nhân nên hiếm. | **Mở** |
| SEC-08 | Trung bình | `pema/api/routers/admin_kb.py`, `pema/knowledge/*` | Kho tri thức nhận mọi tệp do nhân viên tải lên; không có chốt kỹ thuật nào ngăn tài liệu chứa dữ liệu bệnh nhân (SĐT, CCCD). Embedding chỉ gọi `PEMA_EMBEDDING_BASE_URL` (mặc định `ollama` nội bộ, từ chối host công khai nếu không bật `PEMA_EMBEDDING_ALLOW_REMOTE`), nên dữ liệu không rời hạ tầng. Quét tự động bằng `extract_vn_phones` sẽ chặn nhầm số hotline của phòng khám. | **Quyết định**: chế độ cảnh báo hay từ chối khi tài liệu chứa số điện thoại/CCCD; đề xuất cảnh báo trên màn hình duyệt của bác sĩ |

### 2.2 Cơ sở dữ liệu

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-09 | Thấp | `alembic/versions/*` (mọi hàm SECURITY DEFINER) | `SET search_path = pg_catalog, clinic, ctx` có cố định nhưng thiếu `pg_temp` ở cuối, PUBLIC còn quyền TEMP trên database: role chạy được SQL có thể che tên bảng/kiểu bằng đối tượng tạm. | **Đã sửa**: migration `g_0006_definer_search_path` (đặt `pg_temp` cuối cho MỌI hàm definer của `ctx` và `clinic_agent`, thu hồi TEMP của PUBLIC). Test: `tests/test_database.py` |
| SEC-10 | Thấp | `infra/docker-compose.yml` (service `migrate`) | Migration chạy bằng superuser `postgres` nên các view và hàm SECURITY DEFINER (chủ sở hữu bỏ qua RLS) chạy với quyền superuser. Một lỗi trong hàm là toàn quyền DB. | **Mở**: tạo role chủ `pema_owner` NOSUPERUSER cho migration; đã ghi vào báo cáo |
| SEC-11 | Thấp | `0003`, `b1_0004` (`review_item_summary`, `record_outbound_message`) | `agent_worker` đọc được `draft_text`, `payload` của mọi review item cùng phòng khám, và `record_outbound_message` cho worker ghi một tin ra với trạng thái tùy ý. Worker được tin, mọi hàm ghi audit. | Chấp nhận (thông tin) |
| SEC-12 | Thông tin | `0001`..`g_0006` | Đã kiểm bằng test và truy vấn catalog: `agent_worker` không có quyền nào trên schema `clinic`, chỉ SELECT trên 9+1 view `clinic_agent` và EXECUTE trên hàm được cấp; `be_app` không có UPDATE/DELETE/TRUNCATE trên `audit_log` (thêm trigger chặn cả owner); mọi bảng có RLS `clinic_id = ctx.current_clinic_id()` kèm `WITH CHECK`, không có ngữ cảnh thì không có dòng; vai trò runtime không sở hữu bảng nên RLS áp dụng (FORCE không cần); GUC đặt bằng `set_config(..., true)` tham số hóa nên không rò giữa kết nối trong pool; PUBLIC không có EXECUTE trên hàm nào của `ctx`/`clinic_agent`. Giới hạn đã biết: GUC `app.clinic_id` do chính tiến trình tự đặt, nên một tiến trình bị chiếm có thể đọc phòng khám khác trong cùng DB (mô hình một phòng khám của pilot). | Thông tin |
| SEC-13 | Thông tin | toàn `pema/` | Quét AST mọi lời gọi `text/execute/exec_driver_sql` có chuỗi động: 33 chỗ, tất cả chỉ nối hằng danh sách cột hoặc tên cột lấy từ danh sách khóa cố định (`channel_settings.py` dựng `SET col = :col` từ tập khóa cố định; `kb_fts_query.py` dựng bí danh từ chỉ số nguyên, từ khóa đi qua tham số). Không có SQL ghép từ đầu vào. | Thông tin |

### 2.3 Xác thực, phân quyền, API

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-14 | Trung bình | `pema/composition/auth_bridge.py` (`StaffSessionMiddleware`) | Middleware chỉ chặn ẩn danh với 8 họ route admin không tự kiểm quyền; 7 họ admin còn lại (accounts, channels, agents, kb, rules, threads...) và mọi route staff khác dựa vào guard của chính route. Một route thêm sau mà quên guard sẽ mở. Đã xác nhận mọi route hiện tại có guard (xem test), nhưng không có lưới đỡ. | **Đã sửa**: mặc định từ chối. Khi app đã nối dây (`enforce`), MỌI route dưới `/api/v1` không có cookie đều 401 trừ `PUBLIC_API_PREFIXES` (đăng nhập, hai webhook ký). `create_app()` trần vẫn giữ hành vi cũ (test route tự thay dependency). Triển khai thật luôn nối dây: `compose` và `Dockerfile` chạy `uvicorn --factory pema.bootstrap:create_app`, lifespan lỗi thì uvicorn thoát (Starlette gửi `lifespan.startup.failed`), không có đường nào phục vụ app trần. Test: `tests/integration/test_all_routes_refuse_anonymous.py` đi qua toàn bộ OpenAPI (132 thao tác) |
| SEC-15 | Trung bình | `pema/composition/auth_bridge.py` | Các thay đổi qua họ `kb`, `mcp`, `schedules`, `tools` (tải/xóa/duyệt tài liệu, thêm máy chủ MCP kèm header xác thực, tạo lịch gửi, đổi khóa Brave/ảnh) không ghi dòng audit nào (các họ khác ghi trong service). | **Đã sửa**: middleware ghi một dòng `admin.<họ>.<phương thức>` (chỉ đường dẫn và mã trạng thái, không thân yêu cầu) cho mỗi thay đổi thành công. Test cùng file route ẩn danh và `tests/integration/test_admin_audit.py` |
| SEC-16 | Trung bình | `pema/api/body_limit.py` (mới), `webhooks_zalo_*.py` | Hai webhook công khai parse thân JSON trước khi kiểm bí mật; uvicorn không giới hạn thân: một client ẩn danh có thể làm API gom hàng GB. | **Đã sửa**: middleware ASGI cắt thân ở 4 MiB (khai `Content-Length` thì từ chối không đọc; dạng chunk thì đếm), route tải KB có trần riêng nên được miễn. Test: `tests/api/test_body_limit.py` |
| SEC-17 | Thấp | `pema/bootstrap.py` | `/docs`, `/redoc`, `/openapi.json` mở cho ai tới được API, kể cả production. | **Đã sửa**: chỉ mở khi `PEMA_ENVIRONMENT=dev` |
| SEC-18 | Thấp | `pema/api/errors.py`, `dashboard_auth.py`, `auth_bridge.py` | `X-Request-Id` do client gửi được echo vào mọi thân lỗi và lưu vào `audit_log.request_id` không giới hạn (chuỗi dài, ký tự điều khiển). | **Đã sửa**: `pema/api/request_id.py`, chỉ giữ token an toàn dài tối đa 128 |
| SEC-19 | Thấp | `pema_contracts/auth.py` (`LoginRequest`) | Mật khẩu không có độ dài tối đa: chuỗi hàng MB đi vào argon2 (rate limit 5 lần/phút). | **Đã sửa**: `max_length=1024` (OpenAPI tái sinh, `schema.d.ts` không đổi) |
| SEC-20 | Thấp | `pema/api/routers/admin_accounts.py` (`create_account`) | Tạo account với `policy_profile=staff_assistant` chỉ cần `admin.accounts`, trong khi hạ hồ sơ của agent hoặc account có sẵn cần `admin.policy`. Hiện hai quyền cùng thuộc owner và manager nên chưa khai thác được. | **Đã sửa**: cần thêm `admin.policy`. Test: `test_admin_accounts.py` |
| SEC-21 | Trung bình | `pema/composition/intake.py`, `channels/zalo_personal/account_manager.py` | Cổng gửi chủ động của tài khoản cá nhân (kill switch, cửa sổ giờ, trần ngày) dùng `InMemoryProactiveCounter`: trần ngày reset mỗi lần khởi động và tách đôi giữa tiến trình API và worker (gấp đôi trần). Trần của bộ lập lịch (Postgres, nguyên tử) vẫn đúng, nhưng tin chủ động do nhân viên gửi qua API chỉ có trần RAM. | **Đã sửa**: `AccountManager(counter_for=...)` nhận `PgProactiveSendGuard` theo phòng khám (`INSERT ... ON CONFLICT DO UPDATE ... WHERE count < max`). Test: `test_account_manager_kenh.py` |
| SEC-22 | Trung bình | `pema/clinic/actions/conversations.py` (`send_message`), `composition/outbound.py` | Tin nhân viên gửi tay mang cờ `proactive` do client khai (mặc định false). Đặt false cho hội thoại bệnh nhân chưa từng nhắn thì bỏ qua kill switch, cửa sổ giờ, trần ngày, yêu cầu là bạn bè VÀ kiểm tra đồng ý nhận tin (chỉ kiểm khi `proactive=true`). Kill switch của dashboard cũng chỉ có phạm vi `proactive` (bridge hỗ trợ `all` nhưng không có nút). | **Quyết định**: (1) máy chủ tự suy ra `proactive` (không có tin đến trong N giờ thì là chủ động; N do chủ sản phẩm chọn, đề xuất 24); (2) kill switch có chặn cả tin trả lời hay không. Chưa sửa vì làm đổi hành vi nhiều test B1 |
| SEC-23 | Thông tin | `pema/clinic/actions/review_items.py`, `composition/outbound.py` | (tham chiếu SEC-22) tin duyệt từ review item `agent_turn` là trả lời (`proactive=false`), đúng thiết kế. Kiểm lại: review item từ `scheduled_agent`, `crm_rule` được đánh dấu chủ động nên đi qua cổng kênh. | Thông tin |
| SEC-24 | Thấp | `pema/api/dashboard_auth.py` (`refresh`), `routers/auth.py` | Phiên cuốn chiếu: `refresh` luôn gia hạn, không có hạn tuyệt đối. Cookie bị đánh cắp dùng được vô hạn nếu kẻ trộm tiếp tục refresh. Đồng thời API không có route đổi mật khẩu (`change_password`) hay đặt lại mật khẩu (`set_password`) dù action đã viết. | **Đã sửa toàn bộ.** Vòng cuối: `POST /auth/password` (đổi mật khẩu của chính mình, có giới hạn tốc độ, `tests/api/test_dashboard_password_route.py`). Vòng tích hợp H: (1) hạn tuyệt đối của phiên: cột `clinic.auth_session.absolute_expires_at` NOT NULL (migration `b1_0007_session_absolute_expiry`, phiên cũ điền `created_at + 7 ngày`), đặt lúc đăng nhập = `PEMA_SESSION_ABSOLUTE_DAYS` (mặc định 7, hợp lệ 1 đến 30, ngoài khoảng thì từ chối khởi động), `refresh` không dời được, kiểm ở mọi yêu cầu, đăng nhập dọn phiên quá mốc; đổi mật khẩu không dời mốc (`tests/api/test_dashboard_session_absolute.py`); (2) route chủ đặt lại mật khẩu: `POST /api/v1/admin/users/{user_id}/password`, quyền `admin.users` (chỉ chủ), cùng phòng khám (khác phòng khám là 404), không dùng cho chính mình, thu hồi mọi phiên của người bị đặt lại, 5 lần mỗi phút mỗi chủ, audit chỉ ghi ai đặt lại tài khoản của ai, không ghi mật khẩu (`tests/api/test_admin_users_password_route.py`). Vòng H4 (màn Nhân viên, `tests/api/test_admin_users_routes.py`): `GET/POST/PATCH /admin/users` có ba chốt chặn ở backend, không ở màn hình: (a) chủ không tự khóa hay tự đổi vai trò của mình (422); (b) phòng khám luôn còn một chủ đang hoạt động (422; các chủ đang hoạt động bị khóa `FOR UPDATE` trước khi đếm, có test hai chủ hạ nhau cùng lúc); (c) khóa hoặc đổi vai trò thu hồi mọi phiên của người đó và tài khoản khóa không đăng nhập được (nhưng vẫn đặt lại được mật khẩu, và vẫn khóa). Xem danh sách là `admin.users.read` (chủ, quản lý), mọi thay đổi là `admin.users` (chỉ chủ); người khác phòng khám và vai trò `patient` là một 404; tạo giới hạn 5 lần mỗi phút mỗi chủ; audit chỉ ghi tên trường, vai trò, id (không họ tên, email, mật khẩu) |
| SEC-25 | Thông tin | `pema/api/dashboard_auth.py`, `clinic/rbac/passwords.py`, `dashboard_session_store.py` | Đã kiểm: JWT HS256 danh sách thuật toán cố định, bắt buộc `exp/sub/cid/sid`, bí mật tối thiểu 32 ký tự, thiếu thì từ chối đăng nhập; hàng phiên trong DB nên đăng xuất thu hồi thật, đổi mật khẩu loại phiên cũ, vai trò đọc từ DB mỗi lần; cookie `HttpOnly`, `SameSite=Lax`, `Secure` trừ môi trường `dev` (compose đặt `prod`); id phiên mới mỗi lần đăng nhập (không cố định phiên); argon2id, so sánh hằng thời gian, đốt thời gian cho email lạ; đăng nhập sai trả cùng một 401; giới hạn 5 lần/phút theo IP và theo `clinic:email`. CSRF: không có CORS, FE gọi cùng origin qua route handler của Next; `SameSite=Lax` cộng thân JSON đủ cho mô hình hiện tại; nếu API đặt chung tên miền gốc với trang khác, thêm kiểm `Origin`. | Thông tin |
| SEC-26 | Thông tin | `webhooks_zalo_bot.py`, `channels/zalo_bot/*` | Webhook Bot API: bí mật header so bằng `hmac.compare_digest`, không cấu hình bí mật thì từ chối, clinic/account lạ và sai bí mật cùng trả một 401, kiểm bí mật trước khi parse, chống trùng `update_id` nguyên tử trong Postgres và xóa dấu khi route lỗi để Zalo thử lại được. Token bot nằm trong URL path của Bot API: client che token ở mọi thông báo lỗi (ba lớp). | Thông tin |
| SEC-27 | Thấp | `pema/channels/zalo_bot/settings.py` | Bí mật webhook = HMAC-SHA256 của `clinic|account` khóa bằng chính `PEMA_SECRET_ENCRYPTION_KEY` (cùng khóa AES): không tách miền khóa, không xoay được riêng. Rò bí mật webhook không lộ khóa AES. | **Mở**: dùng khóa con HKDF theo nhãn và cho phép xoay |
| SEC-28 | Thấp | `pema/clinic/actions/conversations.py` | `Idempotency-Key` khóa theo `clinic+channel+update_id`, không theo người dùng: hai nhân viên dùng cùng khóa và cùng nội dung nhận lại cùng một tin. Không lộ gì ngoài quyền đã có. | **Mở** (thấp) |

### 2.4 Bí mật và token

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-29 | Thông tin | toàn repo | `git grep` mẫu khóa (`sk-`, `AKIA`, `ghp_`, `xox*`, khóa PEM, JWT ba đoạn), URL có `user:pass@`: không có bí mật thật; hai kết quả duy nhất là mật khẩu hư cấu trong test (`testpw`, `user:pass@host`). `git ls-files`: chỉ có ba tệp `.env.example` toàn giữ chỗ (`change-me-*`), không `.env`, DB, khóa, ghi âm, ảnh bệnh nhân; `.gitignore` chặn `.env*`, `.local/`, `*.pem`, `*.key`. Secret cipher AES-256-GCM: khóa 32 byte đọc từ env, nonce 12 byte ngẫu nhiên mỗi lần mã hóa, thẻ xác thực kiểm khi giải. Mật khẩu role DB truyền bằng `set_config` + `format('%L')` trong migration (không vào lịch sử shell, không vào log). | Thông tin |
| SEC-30 | Thấp | `pema/config/secret_cipher_core.py` (`mask_secret`) | Hiển thị 5 ký tự đầu và 4 cuối: với khóa ngắn (≤ 16 ký tự) lộ hơn nửa. Khóa AES không gắn AAD nên hàng mã hóa có thể bị hoán đổi giữa hai account nếu kẻ tấn công ghi được DB. | **Mở** (thấp) |

### 2.5 SSRF và đầu vào

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-31 | Trung bình | `backend/bridges/zalo-personal/src/url-guard.ts` | Chặn SSRF của `send-video` chỉ khớp dạng chấm của IPv4 nhúng trong IPv6, nhưng parser URL của WHATWG viết `http://[::ffff:127.0.0.1]/` thành `[::ffff:7f00:1]` (đã chạy thử trong Node 22): đi lọt. zca-js gửi HEAD từ máy bridge nên dò được cổng nội bộ và đoán dịch vụ metadata. | **Đã sửa**: đọc 16 byte; chặn `::/96`, mapped `::ffff:0:0/96` và NAT64 theo IPv4 bên trong, 6to4, Teredo, tài liệu, discard, ULA, link-local, site-local, multicast. 43 test (thêm 14 ca) pass |
| SEC-32 | Trung bình | `pema/api/mcp_route_guards.py` (`check_server_url`) | URL máy chủ MCP do admin nhập chỉ kiểm lược đồ và có host: trỏ được tới `http://169.254.169.254/` (metadata), chứa `user:pw@` (khóa nằm trong URL, lưu và hiển thị rõ). | **Đã sửa**: từ chối literal link-local/unspecified/multicast/reserved (kể cả `::ffff:`), tên metadata, user info, cổng sai. Giữ loopback và dải riêng (MCP nội bộ hợp lệ). **Quyết định** còn lại: guard lúc kết nối (chống DNS rebinding) sẽ chặn luôn MCP nội bộ, nên chưa làm. Test trong `test_mcp_routes.py` |
| SEC-33 | Thông tin | `shared/safe_remote_download.py`, `shared/private_address_guard.py`, `shared/download_image.py` | Tải URL ngoài: chỉ http/https; phân giải DNS và kết nối TỚI chính địa chỉ đã kiểm trong cùng một bước (backend mạng `GuardedNetworkBackend`) nên không có cửa sổ DNS rebinding; mỗi hop redirect kiểm lại, tối đa 3; không dùng proxy môi trường; `@` userinfo và dạng số thập phân/hex do thư viện chuẩn hóa trước khi kiểm; IPv6 mapped/NAT64 xét theo IPv4 bên trong; đọc stream có trần byte, giải nén có trần (chống zip bomb HTTP); header thêm là danh sách cho phép. Công cụ web/ảnh/video/tài liệu tắt trong `patient_channel`. Provider tìm kiếm và Jina dùng endpoint hằng. | Thông tin |
| SEC-34 | Thông tin | `knowledge/*`, `shared/xml_sax_scan.py`, `read_zip_entry.py` | Tải tệp KB: kiểm chữ ký thật của tệp, trần thân theo `KB_MAX_FILE_MB` cắt ở tầng đọc, trích xuất chạy trong tiến trình con có timeout và trần RAM; docx/xlsx: trần tổng giải nén 64 MB, một entry 32 MB, tỉ lệ nén 500:1, 256 entry, độ sâu XML 256, tổng ký tự trích 8 MB, DOCTYPE bị từ chối (không XXE, không bom thực thể); tên tệp không bao giờ vào đường dẫn thật (`segment_an_toan` + kiểm `resolve` nằm trong thư mục gốc). | Thông tin |
| SEC-35 | Thông tin | `agent/tools/wrap_untrusted_content.py` và nơi dùng | Nội dung không tin cậy (web_fetch, web_search, kb_search, đầu ra MCP) được bọc nhãn và chống giả dấu phân cách trước khi vào ngữ cảnh. | Thông tin |
| SEC-36 | Thông tin | `video/chay_yt_dlp.py`, `whitelist_nguon_video.py` | yt-dlp: danh sách đối số (không shell), cờ an toàn đặt TRƯỚC đối số của người gọi, môi trường tối thiểu, URL qua danh sách host theo hậu tố, chặn host chuyển hướng; tắt trong `patient_channel`. | Thông tin |
| SEC-37 | Thấp | `shared/web_search_providers.py` | Header `X-Subscription-Token` (khóa Brave) đi theo `follow_redirects=True`; httpx chỉ bỏ `Authorization` khi đổi origin. Endpoint là hằng nên chỉ rủi ro nếu Brave tự chuyển hướng. | **Mở** (thấp) |

### 2.6 Hồ sơ chính sách và gửi tin

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-38 | Thông tin | `policy/hooks.py`, `scheduler/run_context.py`, `channels/*`, `agent/tools/tool_send.py` | Đã lần theo mọi đường ra khách trong `patient_channel`: lời trả lời của lượt (`on_outbound`=`HOLD_FOR_REVIEW`), lời xin lỗi kỹ thuật (cùng cổng), tin định kỳ và việc agent (cổng `decide_outbound` ép review dù hook nói SEND; việc agent chỉ soạn nháp; việc tin chỉ từ template đã duyệt, kiểm lại ở mỗi lần chạy, sinh nhật bị từ chối, `marketingOptOut` chặn), tool gửi trực tiếp (`outbound_refusal`), câu trấn an chờ lâu (tắt bằng `_busy_notice_allowed`, lỗi thì không gửi), MCP (bị lọc ba lớp, danh sách hồ sơ cho phép chỉ gồm `staff_assistant`), `save_memory` (ẩn và chặn ghi từ lời bệnh nhân), tool web/ảnh/video/tài liệu (tắt). Hạ hồ sơ xuống `staff_assistant` cần `admin.policy` (agent, route policy, và nay cả tạo account). Mặc định của account và agent là `patient_channel`; hồ sơ hiệu lực lấy nghiêm ngặt hơn. | Thông tin |
| SEC-39 | Thấp | `agent/tools/add_reaction_tool.py`, `kenh_ca_nhan.auto_react` | Biểu cảm (emoji) gửi thẳng, không qua review, trong cả hai hồ sơ. Không có nội dung chữ. | Chấp nhận / **Quyết định** nếu muốn tắt trong `patient_channel` |

### 2.7 Bridge Node

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-40 | Thấp | `bridges/zalo-personal/src/auth.ts`, `pema/channels/zalo_personal/bridge_signing.py` | HMAC hai chiều đúng (`timestamp.body`, so hằng thời gian, lệch tối đa 300 giây, chữ ký phải đúng 64 hex) nhưng: không có nonce nên một yêu cầu bị bắt trên mạng nội bộ phát lại được trong 5 phút (API→bridge: gửi trùng tin; bridge→API: sự kiện có `update_id` nên bị chống trùng); chữ ký không ràng buộc phương thức và đường dẫn; giao thức chạy HTTP trong mạng docker. | **Mở**: thêm `method + path` vào chuỗi ký và bộ nhớ nonce cho ba route gửi (đổi giao thức hai phía, cần phối hợp với C2) |
| SEC-41 | Trung bình | `infra/docker-compose.yml` (service `zalo-personal-bridge`), `bridges/zalo-personal/src/config.ts` | Lỗi triển khai: compose đặt `PORT`, `PEMA_API_WEBHOOK_BASE` nhưng bridge đọc `PEMA_ZALO_BRIDGE_PORT`, `PEMA_ZALO_BRIDGE_HOST` (mặc định `127.0.0.1`, tức không tới được từ container API), `PEMA_API_BASE_URL`, và cờ `PEMA_ZALO_PERSONAL_ENABLED` (mặc định tắt) không được truyền. Hậu quả: profile `bridge` chạy lên nhưng API không gọi được. Khi sửa, đặt `PEMA_ZALO_BRIDGE_HOST=0.0.0.0` chỉ với `expose` (không `ports`) như hiện tại. | **Đã sửa** (vòng cuối): compose truyền `PEMA_ZALO_PERSONAL_ENABLED`, `PEMA_ZALO_BRIDGE_HOST=0.0.0.0` (chỉ `expose`), `PEMA_ZALO_BRIDGE_PORT`, `PEMA_API_BASE_URL=http://api:8000/api/v1`; ảnh dựng và chạy thật, container thứ hai trong mạng gọi được `/health`. FE: route handler (`src/app/api/[...path]/route.ts`, `healthz/route.ts`) đọc `PEMA_API_INTERNAL_URL` **lúc chạy** ở mỗi yêu cầu (không build arg; `rewrites()` của `next.config.ts` đã bỏ), nên đổi địa chỉ API không cần dựng lại ảnh; chạy thật, `/api/*` và `/healthz` đến được container `api` |
| SEC-42 | Thông tin | `bridges/zalo-personal/*` | Credential chỉ đến qua `POST /v1/accounts/:id/start`, sống trong bộ nhớ zca-js, không ghi đĩa (test `no-disk-write`); không route nào trả credential, cookie hay QR ngoài route QR có chữ ký; logger pino che `cookie`, `imei`, `credential`, `text`, `qr`...; mặc định tắt (chỉ `GET /health`, 503 phần còn lại, zca-js không được nạp); từ chối khởi động nếu bật mà thiếu bí mật 16 ký tự; kill switch trong RAM có phạm vi `all`, API đẩy kèm mỗi lần `start` nên khởi động lại bridge không tắt kill switch; trần theo phút, theo ngày và bộ ngắt sau 5 lần Zalo từ chối; `proactive` BẮT BUỘC trên mọi lệnh gửi. Giới hạn thân 16 MiB. | Thông tin |
| SEC-43 | Thông tin | `pnpm audit`, `pip-audit` | `pnpm audit` (cả dev) cho bridge và frontend: không có lỗ hổng đã biết. `pip-audit -r` trên `uv export --frozen` (53 gói): không có lỗ hổng đã biết. | Thông tin |

### 2.8 Dữ liệu thật trong repo

| ID | Mức | Nơi | Mô tả | Trạng thái |
|---|---|---|---|---|
| SEC-44 | Thông tin | repo | Fixture Office (3 tệp): tên tác giả và người sửa cuối là "Synthetic Author", nội dung là từ dùng thử không dấu ("Ca phe", "25000"), không email hay số điện thoại. SĐT trong test/eval là mẫu rõ ràng (`0900000000`, `0901234567`), tên là tên phổ biến hư cấu; không ảnh, ghi âm, DB hay token bị theo dõi bởi git. | Thông tin |

## 3. Đối chiếu PORT-MAP

Test mới `backend/apps/api/tests/test_port_map_targets.py` (chạy khi có bản clone `E:\Desktop\zalo-agent-ref`, đọc-only) kiểm:

1. Mọi tệp `src/` (519) có hàng trong PORT-MAP và, trừ các hàng `no port`, mọi đường dẫn trong cột đích (`pema/`, `tests/`, `packages/`, `frontend/`, `evals/`) tồn tại thật; hoặc có tệp Python mang header `# ported from:` nhận nguồn đó (bản port nằm ở tên khác với hàng).
2. Mọi tệp Python có `# ported from:` trỏ tới tệp nguồn có thật trong clone.
3. Mọi nguồn được header nêu đều có hàng thật (không phải `no port`) trong PORT-MAP.

Kết quả thật:

| Nhóm | Số lượng | Chi tiết |
|---|---:|---|
| Hàng có đích | 509 | 499 có đủ đích; 10 hàng hứa một tệp test chưa tồn tại đúng tên |
| Trong 10 hàng đó, port nằm ở tên khác (hàng cũ, không thiếu việc) | 8 | `tuning-routes.test.ts` và `vision-routes.test.ts` nằm trong `tests/api/routers/test_admin_model_routes.py`; `overview-routes`, `trace-routes`, `trace-routes-paging`, `log-routes` trong `test_admin_usage_routes.py`; `schedule-routes.test.ts` ở `tests/scheduler/test_schedule_routes.py`; `scheduled-job-send.test.ts` trong `tests/scheduler/test_run_scheduled_job.py` (hai test `test_send_and_conclude_*`) |
| Thiếu thật, đã bù | 1 | `index-startup-order.test.ts` (gói G): viết `tests/test_startup_order.py` (bất biến "nguồn KB treo không khóa dashboard" được giữ bằng cấu trúc hai tiến trình: API không bao giờ chạy worker KB, worker chạy ingest thành task riêng) |
| Thiếu thật, chưa port | 0 | (đã bù ở vòng cuối) `dashboard-password-route.test.ts`: route `POST /auth/password` và `tests/api/test_dashboard_password_route.py` đã có; `KNOWN_MISSING_TARGETS` rỗng |
| Hàng `no port` nhưng đã port | 0 | (đã sửa ở vòng cuối) hai hàng `xoa-han-session` nay trỏ vào `pema/conversation/xoa_han_session.py`; `KNOWN_HEADER_WITHOUT_ROW` rỗng |
| Header trỏ nguồn không tồn tại | 0 | |
| Header không nằm trong cột đích của hàng nguồn | 41 | Thông tin: một tệp Python tách từ một nguồn TS (ví dụ `safe_turn_error.py` từ `provider-error-classifier.ts`); hàng chỉ liệt kê tệp chính |

## 4. Những thứ KHÔNG kiểm tra được và lý do

- **Zalo thật** (Bot API với token thật, tài khoản cá nhân qua zca-js, QR): không có tài khoản/bot thử; toàn bộ kiểm bằng giả lập (`FakeBotClient`, `FakeBridge`, `httpx.MockTransport`). Hành vi thật của Zalo với `secret_token`, thử lại webhook, khóa tài khoản chưa được đo.
- **LLM thật** (Ollama/Qwen3 trên RTX 3060): chưa có máy GPU; kiểm bằng mô hình kịch bản. Khả năng mô hình làm theo prompt injection trong KB/web/MCP chưa đo được; chỉ xác nhận có bọc nội dung không tin cậy.
- **Tailscale, ufw, bind cổng trên máy có IP công cộng, Let's Encrypt thật (chế độ `auto`)**: chưa kiểm. Compose và reverse proxy thì **đã dựng thật** (vòng tích hợp H, Docker Desktop trên Windows): stack `postgres redis migrate api frontend caddy` ở chế độ TLS `internal`, seed demo, đăng nhập thật qua Caddy bằng curl (cookie `HttpOnly`, `SameSite=lax`, `Secure`; `/me` 200; refresh 200; không phải chủ gọi route đặt lại mật khẩu 403; chủ đặt lại mật khẩu nhân viên 204 và phiên cũ của người đó 401, mật khẩu cũ 401, mật khẩu mới 200; tự đặt lại cho mình 422, người lạ 404, ẩn danh 401), header bảo mật có mặt và `Server` bị bỏ, webhook cầu nối từ ngoài 404, `/docs` và `/openapi.json` không tới API, thân quá 4 MiB bị 413. Chưa kiểm: `X-Forwarded-For` với client từ một máy khác (cuộc thử chạy từ chính máy dev, qua loopback), và trình duyệt thật với gốc CA nội bộ.
- **DNS rebinding thật** với mạng ngoài: kiểm bằng đọc code và test đơn vị với resolver giả; không có tên miền xoay địa chỉ.
- **PDF độc hại và OOXML thật nguy hiểm**: chỉ dựa vào test trần giải nén/timeout có sẵn; không fuzz `pypdf`.
- **Linux**: máy kiểm là Windows (vòng lặp selector cho psycopg, yt-dlp qua thread); hành vi trên Ubuntu chỉ suy ra từ code.
- **Danh sách cờ đỏ về mặt lâm sàng**: kiểm tra khả năng bỏ lọt về mặt chuỗi, không đánh giá độ đủ về y khoa (hai nhóm `severe_allergy`, `vascular_vision` vẫn là tạm, chờ bác sĩ).
- **FE (Next.js)**: chỉ `git grep` XSS (`dangerouslySetInnerHTML`, `innerHTML`: không có), lưu token (không có; `localStorage` chỉ giữ giao diện và slug), `target="_blank"` có `rel="noreferrer"`; không rà từng màn.
- **Cạnh tranh thật trên DB** cho trần tin chủ động: dựa vào câu lệnh upsert có điều kiện và test có sẵn, không chạy tải song song.

## 5. Việc mở và quyết định cần người

1. (SEC-22) Chủ sản phẩm: cửa sổ trả lời để máy chủ tự suy ra `proactive`; kill switch có chặn cả tin trả lời không.
2. (SEC-24) Đã sửa toàn bộ (hạn tuyệt đối của phiên, route đổi mật khẩu, route chủ đặt lại mật khẩu); màn Nhân viên (`/admin/users`) đã có và có nút đặt lại; còn lại việc sản phẩm của chủ phòng khám: owner có được khóa hay đặt lại mật khẩu owner khác không (hiện được, trừ chính mình và trừ owner hoạt động cuối cùng).
3. (SEC-08) Chủ phòng khám: cảnh báo hay từ chối tài liệu KB chứa SĐT/CCCD.
4. (SEC-06) Chủ phòng khám: có lưu trace đầu ra tool thô cho `patient_channel` hay không, và số ngày lưu (nay cấu hình được).
5. (SEC-10) F: role chủ `pema_owner` NOSUPERUSER cho migration.
6. (SEC-41) Đã sửa ở vòng cuối (xem hàng SEC-41).
7. (SEC-40) C2: nonce và ràng buộc `method + path` trong chữ ký bridge.
8. (SEC-32) Chủ sản phẩm: có cần guard kết nối cho MCP (đổi lấy việc cấm MCP nội bộ) hay không.
9. (SEC-27, SEC-30, SEC-28, SEC-37, SEC-07, SEC-39) Việc làm cứng mức thấp.

## 6. Kết quả chạy lại sau khi sửa (số liệu thật)

Postgres `pgvector/pgvector:pg17` (`pema-pg-g2`) và Redis 7 (`pema-redis-g2`) chạy container riêng, cổng host ngẫu nhiên, đã xóa sau khi xong.

| Lệnh | Kết quả |
|---|---|
| `uv run ruff check apps/api ../evals` và `ruff format --check` | pass, không lỗi |
| `uv run pyright` (strict) | 0 errors, 0 warnings |
| `uv run lint-imports` | 4 hợp đồng kept, 0 broken |
| `uv run pytest` (có `PEMA_TEST_DATABASE_URL` và `PEMA_TEST_REDIS_URL`) | 4420 passed, 10 skipped, 0 failed (14 phút 17 giây). Sau đó chạy riêng lại các test thêm cuối (`test_database.py`, `test_admin_audit.py`, `test_all_routes_refuse_anonymous.py`): 28 passed |
| Bridge: `tsc --noEmit`, `eslint .`, `prettier --check src`, `node --test` | sạch; 43 test của `url-guard` pass (thêm 14 ca) |
| `pnpm audit` (bridge, frontend), `pip-audit` | không có lỗ hổng đã biết |
| `pnpm run gen:types` | `schema.d.ts` không đổi sau khi OpenAPI thêm `maxLength` |

### Chạy lại ở vòng tích hợp H (gộp H1, H2, H3)

Postgres `pgvector/pgvector:pg17` (`pema-pg-hi`) và Redis 7 (`pema-redis-hi`) container riêng, cổng host ngẫu nhiên, đã xóa sau khi xong.

| Lệnh | Kết quả |
|---|---|
| `alembic upgrade heads` trên DB sạch; `alembic heads` | lên tới `h_0008_merge_heads`; một đầu duy nhất |
| `ruff check`, `ruff format --check` (backend và `../evals`), `pyright` strict, `lint-imports` | sạch; 0 errors; 4 hợp đồng kept |
| `uv run pytest` (có `PEMA_TEST_DATABASE_URL` và `PEMA_TEST_REDIS_URL`, gồm `../evals`) | 4531 passed, 10 skipped, 0 failed (11 phút 7 giây). Lần chạy đầu có 3 test của retention hỏng vì hàm seed `auth_session` chưa điền cột `absolute_expires_at` NOT NULL của H1; đã sửa `pema/retention/pg_testing.py` rồi chạy lại toàn bộ |
| Frontend: `eslint`, `tsc --noEmit`, `vitest run`, `next build`, `prettier --check`; `gen:types` | sạch; 230 test pass; `schema.d.ts` và `openapi.json` không đổi sau tái sinh |
| Bridge: `eslint`, `tsc --noEmit`, `prettier --check`, `node --test` | sạch; 296 test pass |
| `docker compose config` (mặc định, `app`+`bridge`, mọi profile, `proxy` + `docker-compose.proxy.yml`) | hợp lệ cả bốn |
| Stack thật qua Caddy (`internal`), seed demo, đăng nhập bằng curl, đặt lại mật khẩu; `python -m pema.workers.retention --dry-run` trong container `api` và `worker` | như mục 4 (dòng Compose/proxy); dry-run: `status=done`, mọi số đếm 0, nhóm giữ mãi được liệt kê |
