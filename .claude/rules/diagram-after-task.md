# Vẽ sơ đồ sau khi xong task

Áp cho mọi task đã xong và đã qua test. Sơ đồ phản ánh code vừa làm, không vẽ trước.

- **Task đụng tới DB** (migration, thêm/sửa/xóa bảng, cột, index, role, schema, đổi quan hệ giữa các bảng): chạy skill
  `/archify` vẽ lại ERD của schema `agent_rt` (bản đang có: `.archify/erd-agent-rt-20261022-171500/`).
- **Task đụng tới cấu trúc hệ thống code** (thêm hay bỏ plugin, tool, service, route, luồng dữ liệu, ranh giới của agent,
  thứ tự gọi giữa các thành phần): chạy skill `/archify`; kết quả nằm trong `.archify/<loại>-<tên>-<giờ>/`.
- Task chỉ sửa lỗi nhỏ, đổi tên, sửa chữ, sửa test hay tài liệu mà không đổi bảng hay luồng thì không cần vẽ.
- Cuối báo cáo của task, ghi một dòng: đã vẽ gì và ở file nào, hoặc "không vẽ" kèm lý do.
- Sơ đồ chỉ là tài liệu: không sửa code hay luật khác để cho khớp với sơ đồ. Commit sơ đồ theo quy định git của repo
  (không ghi tên AI).
