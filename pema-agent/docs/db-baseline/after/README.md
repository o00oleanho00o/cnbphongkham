# Schema sau baseline (bước 8–9 của PLAN-db-baseline)

`clinic_ctx.sql`: `pg_dump -s -n clinic -n ctx --no-owner` của một database trắng chạy `0001_baseline`.
So với mốc `../before/` chỉ khác ở các chỗ kế hoạch đã chốt:

| Khác biệt | Lý do |
|---|---|
| Không còn schema `agent` (28 bảng), `clinic_agent` (13 view, 12 hàm) | C1–C7, D5, luật L3 |
| Không còn role `agent_worker` trong database này, không grant nào cho nó | D5, L1 |
| Bỏ extension `vector` | Chỉ schema `agent` cũ dùng; agent tự tạo trong DB của nó |
| Bỏ 19 bảng `clinic`: `conversation`, `message`, `review_item`, `channel_identity`, `conversation_assignment`, `account_roster`, `message_template`, `sla_check`, `notification_outbox`, `notification_log`, `push_token`, `notify_setting`, `notify_preference`, `notify_link_code`, `identity_link_attempt`, `identity_link_code`, `channel_setting`, `on_call_contacts`, `patient_ownership` | D8 (Hộp thư, Theo dõi, mẫu tin, thông báo O3); ba bảng cuối không code nào dùng |
| Bỏ hàm `record_inbound_message`, `record_outbound_message`, `create_review_item`, `retention_purge_link_attempts`, view `review_item_summary`, trigger guard tài khoản | D8, C3 |
| `clinic.record_retention_run` chuyển từ `clinic_agent` sang `clinic`, chỉ nhận phạm vi `clinic` | C7; retention không còn phạm vi agent |
| Thêm `clinic.guide_article` | D1 (trang Hướng dẫn) |
| `crm_rule` bỏ cột `send_mode` và CHECK sinh nhật | D8: luật CRM chỉ tạo việc |
| `staff_profiles` bỏ `skills`, `capacity`, `languages`, `notify_zalo_*` | Của care agent và chuông Zalo O3, không còn code dùng |
| `patient_app_event.kind` chỉ còn `aftercare` | D8: bỏ "Nhắn tin" vào app |
| Không còn dòng `protocol` `laser-co2` trong migration | D4: seed demo (`catalog_seed`) tạo khi thiếu |

Giữ nguyên: mọi bảng, cột, ràng buộc, trigger và quyền `be_app` khác của `clinic`/`ctx`; dòng `clinic` duy nhất tạo từ
`PEMA_CLINIC_NAME` / `PEMA_CLINIC_ID`; PUBLIC không có quyền TEMP trên database.

## `agent_rt.sql` (bước 10)

`pg_dump -s -n agent_rt --no-owner` sau `alembic upgrade head` (`0001_baseline`) rồi `agent db migrate-plugins`.
**Trùng từng dòng** với chuỗi cũ (12 revision + 9 file plugin) chạy trên một database trắng, kể cả quyền của
`agent_rt_app`. Khác ở cách đi tới:

| Trước | Sau |
|---|---|
| 12 revision `0001_agent_rt` … `0012_plugin_migrations` | `0001_baseline` (đọc `0001_baseline.sql`) |
| `conversations`: `0001_conversations`, `0002_scenarios` | `0001_conversations.sql` |
| `knowledge`: `0001_create_store`, `0002_vectors`, `0003_bm25` | `0001_create_store.sql` |
| `skills`: `0001_items`, `0002_import_agent_skills`, `0003_seed_dev_skill`, `0004_drop_agent_skill` | `0001_items.sql`, `0002_seed_dev_skill.sql` |
| bảng `agent_skill` tạo ra rồi xóa | không còn bước nào nhắc tới |

Bước 11 chuyển schema này sang database riêng `pema_agent`.
