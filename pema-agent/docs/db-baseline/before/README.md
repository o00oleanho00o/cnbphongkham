# Mốc "trước" (bước 1 của PLAN-db-baseline), 2026-10-16

Chuỗi migration cũ của cả hai app chạy trên database tạm `scratch_before` (cùng cluster Docker, không đụng `pema`), rồi
`pg_dump -s --no-owner` từng schema. Bước 9 và 11 so bản dump của baseline mới với các file này.

| Schema | Bảng | Ghi chú |
|---|---|---|
| `public` | 2 | hai bảng phiên bản alembic; extension `vector`, `plpgsql` |
| `ctx` | 0 | hàm `the_clinic_id()` |
| `clinic` | 53 | API phòng khám |
| `clinic_agent` | 0 | 13 view, các hàm cho agent cũ (bỏ theo L3) |
| `agent` | 28 | app zalo-agent cũ (bỏ) |
| `agent_rt` | 24 | agent app (sau khi plugin skills `0004` xóa `agent_skill`) |

Quyền thật (`privileges.txt`): `agent_rt_app` chỉ có USAGE trên `agent_rt` và `public`, nhưng **cùng database** với CRM.
`be_app` có toàn quyền DML trên `agent` (28 bảng) và `clinic`. `agent_worker` còn toàn quyền trên `agent` dù không tiến trình
nào dùng. Không có `dblink` hay `postgres_fdw`.

Test xanh trước khi làm: agent `687 passed, 65 skipped` (không DB; cả bộ); API: xem dòng dưới.

API: bộ đầy đủ trên code cũ chưa đo xong (chạy quá lâu, đã dừng). Sau bước 6, ops + clinic: 876 passed; 5 đỏ đã ghi trong báo cáo bước 6.
