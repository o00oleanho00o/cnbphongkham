# Viết hoặc sửa code: chỉ test UI end-to-end, không viết unit test

Áp cho mọi lần viết hoặc sửa code trong repo này (`pema-agent/` backend, agent, plugin, frontend), kể cả do subagent làm.
Chủ hệ thống chốt (2026-10-23): đã xóa hết unit test của backend, agent, plugin, cầu nối Zalo và frontend; chỉ còn test
end-to-end qua UI.

- **Test duy nhất là e2e qua UI**: Playwright trong `pema-agent/frontend/e2e/` (`bun run e2e`), chạy trên stack thật
  (trình duyệt → frontend → API/agent → DB). Tính năng nhìn thấy trên màn hình: viết hoặc sửa spec e2e của nó.
- **Không viết unit test**, kể cả cho phân quyền, bảo mật, DB, động cơ ca hay quy tắc thuần. Không thêm `tests/`,
  `test_*.py`, `*.test.ts`, `conftest.py` hay mô-đun hỗ trợ test. Nếu một thứ UI không thể thấy (quyền DB, token, import
  giữa lớp, luật L1–L7 và H1–H11) thì chủ chấp nhận không có test: tự đối chiếu với luật trong `agent-crm-boundary.md` và
  `agent-harness.md` trước khi báo xong, và nói trong báo cáo đã đối chiếu những luật nào.
- Chủ là người chạy e2e: cần stack đang chạy (cấu hình và biến môi trường trong `frontend/e2e/playwright.config.ts`, đăng
  nhập trong `session.ts`). Không tự dựng lại Docker, không đụng DB demo `pema`, chỉ chạy khi chủ bảo.
- Không có test thì kiểm bằng cách nào: xem `code-checks.md` (chỉ cần `bun run build` không lỗi và backend khởi động được).
- Cuối báo cáo của task có code mới, ghi một dòng: spec e2e nào đã viết hoặc sửa, hoặc "không viết test" kèm lý do.
