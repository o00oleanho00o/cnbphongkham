# Kế hoạch: bỏ app zalo-agent cũ, cắt chỗ chéo, khóa ranh giới agent ↔ CRM, làm lại DB

Ngày: 2026-10-16. Trạng thái: **xong cả 13 bước (nhánh `chore/db-baseline`), DB demo đã dựng lại 2026-10-16.** FE đã dọn theo D8 (commit ccf9d6b9). Sơ đồ: [diagrams/db-baseline-plan.html](diagrams/db-baseline-plan.html).

Bạn xóa DB, nên không cần đường nâng cấp từ DB cũ. Hai app vẫn tách riêng (không dồn chung một chuỗi migration).

## 1. Luật bất biến: agent không bao giờ chạm được CRM

Agent nói chuyện với người ngoài (Zalo, web) nên **phải coi như có ngày bị jailbreak**. Khi đó nó chỉ được phá trong vùng của nó.

| # | Luật | Cách giữ (không dựa vào lời dặn model) |
|---|---|---|
| L1 | Agent không đọc ghi được DB của CRM | **Hai database riêng** trên cùng Postgres: `pema` (API) và `pema_agent` (agent). Role `agent_rt_app` chỉ có CONNECT vào `pema_agent`; Postgres không truy vấn chéo database (không cài `dblink`, `postgres_fdw`) |
| L2 | Agent không gọi được API của CRM | Agent không giữ khóa, mật khẩu hay tài khoản dịch vụ nào của API. API từ chối mọi token không phải phiên nhân viên của chính nó, kể cả token SSO có `aud = pema-agent` mà nhân viên mang sang agent |
| L3 | Không có "cửa sổ cho agent" bên CRM | Bỏ schema `clinic_agent` (view và hàm làm riêng cho agent cũ), bỏ role `agent_worker`. Hàm nào API còn dùng thì chuyển về schema `clinic` |
| L4 | Dữ liệu phòng khám vào agent chỉ theo một đường | Nhân viên tải tài liệu đã duyệt lên kho tri thức của agent. Không tool nào của agent tra bệnh nhân, lịch hẹn, đơn, tài chính |
| L5 | Muốn mở đường mới thì người chủ hệ thống quyết | Ghi vào `.claude/rules/agent-crm-boundary.md` (AI và subagent đều đọc); đường mới phải hẹp, chỉ đọc, có nhân viên duyệt, và có thiết kế riêng |

**Test giữ luật** (chạy trong bộ test, hỏng là đỏ):

- T1 (agent, `db`): `agent_rt_app` không CONNECT được database `pema`; không có USAGE trên schema nào ngoài `agent_rt` và `public`.
- T2 (api, `db`): `be_app` không CONNECT được `pema_agent`; database không có extension `dblink` hay `postgres_fdw`.
- T3 (api): token có `aud = pema-agent` bị mọi route của API từ chối.
- T4 (agent): profile `clinic` không có plugin nào cấu hình URL của API ngoài `sso.jwks_url`.

## 2. Hiện trạng (đã kiểm trên code; Docker đang tắt nên chưa đọc quyền thật trên DB)

- Agent kết nối bằng `agent_rt_app` nhưng **vào chung database `pema`** (`infra/docker-compose.yml:231`). Ranh giới hiện chỉ là
  `REVOKE ALL ON SCHEMA clinic FROM PUBLIC` (`0001_clinic_schema.py:137`): một lệnh GRANT nhầm sau này là agent đọc được bệnh nhân.
- Agent không có biến môi trường nào chứa khóa API; nó gọi API duy nhất để lấy JWKS (`agents/clinic/agent.toml:69`).
- `bootstrap-roles.sh:85` cấp CONNECT cho `agent_worker` (role của agent cũ, không còn tiến trình nào dùng).
- Schema `clinic_agent` là cửa sổ của agent cũ: 13 view và các hàm `record_inbound_message`, `create_review_item`, … Phần API còn
  gọi: `inbox_ingest.py` (chỉ test gọi?), `retention/rules.py:213-214` (hàm audit và purge), `templates.py`.

## 3. Chỗ chéo phải cắt (schema `agent` cũ, 28 bảng)

| # | Chỗ chéo | Bằng chứng | Cách cắt |
|---|---|---|---|
| C1 | Trang Hướng dẫn đọc `agent.kb_document`, `agent.kb_chunk` | `clinic/actions/guide.py:79,112,142,185`; frontend gọi `/guide/articles`, `/guide/ask` | Bảng riêng `clinic.guide_article` + tìm full-text (D1) |
| C2 | Vòng CRM JOIN `agent.accounts` | `crm_rules/sql_store.py:223` | Bỏ JOIN; dùng cột `channel_account` của `clinic.conversation` (D3) |
| C3 | FK `clinic.conversation.account_id`, `clinic.account_roster.account_id` → `agent.accounts`; trigger `conversation_account_guard`, `account_purpose_guard` | `o1_0010_identities_roster.py:306-383` | Cột text không FK; bỏ hai trigger. Nếu kiểm ra inbox và roster không còn ai ghi thì xóa luôn (D3) |
| C4 | `agent.runtime_settings` đọc lúc khởi động (luôn rỗng) | `config/runtime_settings_store.py:83-108` | Bỏ phần ghi đè tuning |
| C5 | Hệ KB cũ: `pema/knowledge/*`, route `/admin/kb/*` (không trang nào gọi), vòng nạp KB | báo cáo khảo sát | Xóa (trang Hướng dẫn đã chuyển ở C1) |
| C6 | Code chết đi kèm | `retention/rules.py` (`AGENT_RULES`), `roster.py` phần không gọi được, `outbound._resolve_identity`, seed trong `pg_testing.py`, `.pyc` mồ côi, route cũ trong `frontend/src/lib/api/schema.d.ts` | Xóa |
| C7 | Schema `clinic_agent`, role `agent_worker` | mục 2 | Bỏ (L3); hàm còn dùng chuyển về `clinic` |

## 4. Quyết định cần bạn chốt (có khuyến nghị)

| # | Câu hỏi | Khuyến nghị |
|---|---|---|
| D1 | Trang Hướng dẫn lưu ở đâu? | `clinic.guide_article` trong API |
| D2 | Quyền `be_app` | Giữ đúng quyền đang có hiệu lực; siết quyền là việc riêng, có test |
| D3 | Tài khoản kênh trong `clinic` | Cột text, không FK, bỏ trigger; phần nào không ai ghi thì xóa |
| D4 | Dữ liệu trong migration | Giữ dòng `clinic` (từ biến môi trường); `laser-co2` chuyển sang seed demo |
| D5 | `clinic_agent`, `agent_worker` | Bỏ (L3) |
| D6 | Test kiểm lịch sử migration | Xóa; kiểm schema cuối thì chuyển thành test schema |
| D7 | Hai database riêng `pema` / `pema_agent` | **Có** (L1). Rẻ nhất là làm ngay lúc dựng lại DB |
| D8 | Hộp thư, Theo dõi, mẫu tin, nhắn tin vào app | **Bỏ hết** (chủ hệ thống chốt 2026-10-16): không kênh nào đổ tin vào CRM; kết quả "chuyển bác sĩ" của CRM chỉ còn ghi ở nhật ký liên hệ; luật CRM chỉ tạo việc cho nhân viên; app bệnh nhân bỏ loại "Nhắn tin", giữ "aftercare". Danh sách ở mục 5a. FE dọn ở đợt sau |
| D9 | Design (canvas, `design-specs/web`) | **Không động tới** trong kế hoạch này và đợt dọn FE |

## 5. Các bước (mỗi bước nhỏ, một commit, test xanh, app vẫn chạy; ⏸ = tôi dừng chờ bạn)

**A. Chuẩn bị**

0. Bạn commit phần dọn skill đang dở; tôi mở nhánh `chore/db-baseline`.
1. ⏸ Chụp mốc: DB tạm chạy chuỗi migration cũ, `pg_dump -s` ra `docs/db-baseline/before/`, ghi số test xanh của hai app.
2. Viết luật `.claude/rules/agent-crm-boundary.md` (L1–L5) và test T3, T4 (đúng ngay bây giờ). T1, T2 viết ở bước 11.

**B. Cắt chỗ chéo (chỉ sửa code API; migration cũ vẫn nguyên)**

3. C4: bỏ đọc `agent.runtime_settings`.
4. ⏸ C1: trang Hướng dẫn chuyển sang `clinic.guide_article` (revision tạm, gộp vào baseline sau); `seed_guide` ghi bảng mới.
5. ⏸ C2, C3: CRM, inbox, roster thôi dùng `agent.accounts`; kiểm ai còn ghi inbox và roster rồi quyết giữ hay xóa.
6. C5, C6: xóa KB cũ và code chết.
7. C7: hàm `clinic_agent` còn dùng chuyển về `clinic` (sửa chuỗi SQL ở chỗ gọi); kiểm `grep` không còn `agent.`, `clinic_agent.`
   trong code API; cả bộ test API xanh.

7b. ⏸ D8: bỏ Hộp thư, Theo dõi, mẫu tin, nhắn tin vào app (danh sách ở mục 5a). Bảng không cần revision tạm: baseline
   bước 8 không tạo chúng.

**C. Baseline API**

8. ⏸ `0001_baseline` cho API: chỉ schema `ctx` và `clinic`; role `be_app` (D2); hàm, trigger ở dạng cuối; dòng `clinic` từ biến môi
   trường; không có `agent`, `clinic_agent`, RLS cũ, `agent_worker`. Xóa 30 revision cũ; sửa test theo D6, fixture, `infra/scripts/*`,
   `Makefile`.
9. ⏸ So sánh `pg_dump -s` với mốc: chỉ được khác ở đúng danh sách mục 3 và D1–D7. Cả bộ test API.

**D. Baseline agent và database riêng**

10. `0001_baseline` cho `agent_rt`; mỗi plugin một file `0001_*.sql`; skill mẫu thành `0002_seed_dev_skill.sql`; sửa test.
11. ⏸ D7: compose tạo database `pema_agent`, `agent-migrate` và `agent` trỏ sang đó; `db_roles.py` chỉ cấp CONNECT trên
    `pema_agent`; `bootstrap-roles.sh` thôi nhắc `agent_worker`; backup cả hai database. Viết test T1, T2. So sánh `pg_dump -s`.
    Cả bộ test agent và test `db` trên DB tạm.

**E. Dựng lại**

12. Tài liệu nhắc số revision (README, `infra/README.md`, `docs/*`), viết lại HANDOFF.
13. ⏸ Bạn xóa DB và volume, build lại Docker. Tôi chạy smoke (API, agent, đăng nhập, Hướng dẫn, chat Zalo và web, nạp tài liệu) và
    **thử phá ranh giới trên hệ thật**: từ container agent thử kết nối `pema`, thử gọi route CRM bằng token SSO → cả hai phải bị từ chối.

## 5a. Danh sách bước 7b (D8)

**Xóa hẳn (API, `apps/api/pema`)**

- Route: `routers/conversations.py`, `assignment.py`, `review_items.py`, `admin_templates.py`.
- Action: `clinic/actions/conversations.py`, `assignment.py`, `_assignment_core.py`, `inbox_ingest.py`, `outbound.py`,
  `review_items.py`, `roster.py`, `sla_checks.py`, `templates.py`.
- Live: `live/presence.py` và hai route presence; loại sự kiện `inbox.changed`, `review.changed`, `presence.changed`,
  `assignment.changed`, `notifications.changed`, `handoff.changed`.
- Model: `clinic/models/inbox.py`; trong `ops.py` mọi lớp trừ `StaffProfile`.
- Contracts (`packages/contracts`): `conversations.py`, `review.py`, phần mẫu tin, roster, phân công trong `ops.py`,
  `admin.py`; mã lỗi `thread_locked`, `review_required` nếu không còn ai dùng.
- Quyền RBAC: `conversation.read/reply`, `review.read/decide/decide_clinical`, `roster.read/manage`,
  `thread.claim/assign/end_shift`, `agent.submit`.
- Retention: luật xóa tin nhắn, mục Theo dõi, `identity_link_attempt`, `identity_link_code`.
- Test của các phần trên (`tests/ops/*` phần lớn, `test_api_conversations_reviews.py`, `test_assignee_validation.py`,
  test presence, review, template...).

**Sửa (giữ chức năng, bỏ nhánh liên quan)**

- `crm_tasks.py`: kết quả `doctor`, `reaction`, `complaint` thôi tạo mục Theo dõi, chỉ ghi nhật ký liên hệ.
- `crm_rules/*`: bỏ `template_key`, chế độ gửi khác `staff_task`, đích kênh (`channel_identity`); chỉ còn tạo việc.
- `patient_app.py`: bỏ loại `message`; `patient_360.py`: bỏ mục tin nhắn và hội thoại trong dòng thời gian.
- `live_access.py`, `dashboard_auth.py`, `api/router.py`, `actions/__init__.py`, `models/__init__.py`, `rbac/matrix.py`,
  `seed_demo.py`, `clinic_testing.py`, `config/env.py` (biến retention của tin nhắn), `openapi.json`.

**Bảng không còn trong baseline (bước 8)**

`conversation`, `message`, `review_item`, `channel_identity`, `conversation_assignment`, `account_roster`,
`message_template`, `sla_check`, `notification_outbox`, `notification_log`, `push_token`, `notify_setting`,
`notify_preference`, `notify_link_code`, `identity_link_attempt`, `identity_link_code`; thêm ba bảng không code nào dùng:
`channel_setting`, `on_call_contacts`, `patient_ownership`. Hàm SQL `record_inbound_message`, `record_outbound_message`,
`create_review_item`, view `review_item_summary` cũng bỏ.

**Giữ:** `staff_profiles`, `assignees.py` và `/staff/assignable` (CRM giao việc vẫn dùng), luồng live cho lịch hẹn và
việc CRM.


## 6. Quy ước về sau

- Mỗi app một chuỗi migration thẳng từ `0001_baseline`; mỗi thay đổi một revision nhỏ có `downgrade`.
- Dữ liệu mẫu ở lệnh seed, không ở migration.
- Không bảng nào của app này đọc bảng của app kia; nối qua HTTP, và agent không có khóa API của CRM (L2).
- Mọi tool hay plugin mới của agent phải qua luật `agent-crm-boundary.md`; T1–T4 đỏ là không merge.

## 7. Rủi ro

- Mất toàn bộ dữ liệu demo (bạn đã chấp nhận): key và cấu hình model phải nhập lại.
- Bước 4, 5 đổi hành vi thật (Hướng dẫn, CRM, inbox); có test riêng và dừng chờ bạn.
- Chưa đọc quyền thật trên DB (Docker tắt): bước 1 đọc lại và ghi vào mốc.
- Nếu chọn siết quyền `be_app` (D2 khác khuyến nghị) có thể vỡ âm thầm vì chưa có test quyền.
