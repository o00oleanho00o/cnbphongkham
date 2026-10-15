# Kế hoạch: skill chỉ cất ở một nơi (DB, plugin `skills`)

Ngày: 2026-10-15. Trạng thái: **đã làm xong cả 6 bước, chưa commit** (xem mục 6 cho những chỗ làm khác kế hoạch).

## 1. Vì sao

Hiện có hai luồng cất skill chạy song song:

| | Core (`agentcore/skills`) | Plugin `skills` |
|---|---|---|
| Nơi cất | bảng `agent_skill` (+ thư mục `SKILL.md` đóng gói sẵn) | bảng `sk_item`, `sk_item_version` |
| Phạm vi, phiên bản, trang quản trị | không | có (agent / plugin / kênh, lịch sử, Studio) |
| Tool | `skill_list`, `skill_view`, `skill_write`, `skill_patch` | `skill_list`, `skill_view`, `skill_search`, `studio_*` |
| Agent đang dùng | `dev` | `clinic` |

Hai bộ tool trùng tên. Registry ném `ValueError: Tool already registered` nếu một agent bật cả hai. Quyết định của chủ hệ thống: **mọi skill nằm trong DB, không còn file làm nguồn thật** (sau này chạy hết trên container).

## 2. Quyết định đã chốt

- Một nơi cất duy nhất: `sk_item`.
- Thư mục `SKILL.md` đóng gói sẵn bỏ hẳn (hiện chỉ có `agents/dev/skills/write-a-plan/SKILL.md`), nạp một lần vào DB.
- Agent được tự ghi skill, có hiệu lực ngay. **Không làm chế độ duyệt/nháp cho agent** và **không thêm cột nào**: bật/tắt dùng cột `status` đã có (`active` / `archived`). Chế độ `draft` của chat Studio giữ nguyên, không đụng tới.

## 3. Các bước

Mỗi bước một commit. Dừng sau bước 3 để kiểm tra trước khi gỡ core.

1. **Tool ghi skill trong plugin `skills`.** Thêm `skill_write` (ghi hoặc cập nhật, `status='active'`, `origin='agent'`) và `skill_patch` (thay một đoạn, lưu một phiên bản như mọi lần sửa). Cùng bước kiểm tra như mục viết bằng cách khác. Phạm vi mặc định: kênh hiện tại (hẹp nhất); đọc `scope.py` để chốt khi làm.
2. **Nạp `write-a-plan` vào DB.** Migration trong `plugins/skills/migrations/`: `kind='skill'`, `origin='admin'`, `status='active'`, cho agent `dev`, bỏ qua nếu tên đã có (như `0002`). Xong xóa `agents/dev/skills/`.
3. **Chuyển `dev` sang plugin.** `agents/dev/agent.toml`: thêm `skills` vào plugin bật, `[skills] enabled = false`.
4. **Gỡ phần core.** `agentcore/skills/` (`library`, `tools`, `__init__`); mục "skills" trong `prompt/builder.py` và `prompt/data.py`; `assembly.py`, `runtime.py`, `profile.py` (`[skills]`, `bundled_skills_dir`); `PostgresSkillStore` trong `storage.py`; `db_roles.py`; mục `[skills]` trong hai `agent.toml`.
5. **Xóa bảng `agent_skill`.** Revision alembic mới (bảng do `alembic/versions/0001_agent_rt.py` tạo, không sửa bản cũ). Làm sau cùng.
6. **Test.** Sửa/xóa `packages/agent-core/tests/test_skills.py`, `tests/test_storage.py`, `tests/test_plugins.py`; thêm test cho `skill_write` / `skill_patch` ở `tests/skills/test_skills_db.py`.

## 4. Rủi ro và điều kiện

- Skill agent tự ghi có hiệu lực ngay. Ở kênh khách, một skill sai áp dụng cho mọi cuộc trò chuyện cùng phạm vi từ lần sau. Giảm rủi ro: phạm vi hẹp, nhân viên cất được trên Studio. **Khuyến nghị: chỉ đăng ký hai tool ghi cho `dev`, không cho kênh khách (Zalo).** Cần chủ hệ thống chốt.
- Bước 4 sửa `agentcore` (gói dùng chung): chạy test của gói và test các agent.
- Bước 5 không đảo ngược nếu còn skill chưa chuyển. **Trước đó đếm số dòng `agent_skill` trên DB demo**, và chỉ chạy khi chủ hệ thống xác nhận.
- Migration chạy khi build lại Docker (`agent-migrate`); build do chủ hệ thống quyết.

## 5. Chưa kiểm chứng (kiểm khi làm)

- Nút "Cất" trên Studio có đổi `status` sang `archived` không, và agent có bỏ mục `archived` khi dựng mục lục không.
- Mục "skills" trong `prompt/builder.py`: bỏ đi thì prompt của agent có đổi không (so sánh trước và sau).
- Plugin `skills` có cần `ready()` / bảng sẵn trước khi `dev` chạy lần đầu không.

## 6. Đã làm, và chỗ khác kế hoạch

- Bước 1: `skill_write` / `skill_patch` nằm trong `plugins/skills/plugin.py`, chỉ đăng ký khi cấu hình `agent_writes = true`
  (dev bật, clinic không). Có `prompt_args` nên hook chống chèn lệnh vẫn quét như tool cũ. Agent chỉ sửa được mục có
  `origin = agent`. Phạm vi mặc định: `channel:<kênh>` nếu kênh thuộc một plugin chat (Zalo), ngược lại cả agent. Câu nhắc
  "ghi skill khi tìm ra cách làm đáng dùng lại" chuyển từ prompt lõi sang đoạn ngữ cảnh của plugin.
- Bước 2: `0003_seed_dev_skill.sql` (`origin = admin`, vì cột không có giá trị `bundled`); thư mục `agents/dev/skills/` đã xóa.
- Bước 3: `agents/dev/agent.toml` bật plugin `skills` và `agent_writes`.
- Bước 4: gỡ `agentcore/skills/`, mục prompt "skills", `SkillEntry`, `SkillsSection`, `bundled_skills_dir`, `PostgresSkillStore`,
  `skill_store` trong `build_agent` / `runtime`, và `[skills]` + tên mục "skills" trong hai `agent.toml`. Một khóa `[skills]`
  còn sót trong profile cũ vẫn tải được (profile cho phép khóa thừa ở cấp trên cùng) và bị bỏ qua.
- Bước 5: **khác kế hoạch**: xóa bảng bằng migration của plugin (`0004_drop_agent_skill.sql`), không phải revision alembic.
  Lý do: `0002` của plugin đọc `agent_skill` và các file migration plugin không được sửa sau khi chạy; alembic chạy trước
  plugin, nên xóa ở alembic làm `migrate-plugins` hỏng trên DB mới. Đếm trên DB demo: `agent_skill` 0 dòng. `agent_skill`
  cũng bỏ khỏi `db_roles.DATA_TABLES`. Revision alembic 0001/0002 giữ nguyên, nên **hạ cấp alembic sau khi plugin đã xóa bảng
  sẽ lỗi** (chưa xử lý).
- Bước 6: thêm 5 test cho hai tool và cho cấu hình dev (`tests/skills/test_skills_plugin.py`), 1 test DB cho hạt giống và việc
  bảng đã mất; xóa test của lõi (`test_skills.py`, hai test trong `test_storage.py`, test skill đóng gói trong
  `test_agent_app.py`); sửa `test_plugins.py` (giữ ghi chú qua lần rebuild thay vì skill) và cassette (thêm `skill_search`).
- Kiểm: agent-core 229 passed; apps/agent 687 passed, 65 skipped (không DB); các test `db` trên database tạm: 63 passed, 2 failed
  vì `DROP ROLE agent_rt_app` bị chặn (role còn đối tượng ở DB demo `pema`), không liên quan thay đổi. Chưa build lại Docker:
  migration 0003, 0004 chạy khi `agent-migrate` chạy.
