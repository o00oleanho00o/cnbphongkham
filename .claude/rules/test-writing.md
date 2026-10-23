# Viết hoặc sửa code: ưu tiên test UI end-to-end, cấm viết unit test bừa bãi

Áp cho mọi lần viết hoặc sửa code trong repo này (`pema-agent/` backend, agent, plugin, frontend), kể cả do subagent làm.
Chủ hệ thống chốt (2026-10-23). Luật này nói **viết test gì**; `testing.md` nói **chạy test nào**.

- **Mặc định là test end-to-end qua UI.** Tính năng nhìn thấy được trên màn hình (nút, trang, hộp thoại, luồng) được kiểm
  bằng test Playwright trong `pema-agent/frontend/e2e/` chạy trên stack thật (trình duyệt → frontend → API/agent → DB),
  không bằng unit test của màn hình hay của route. Muốn thêm hay sửa tính năng có UI: viết hoặc sửa spec e2e của nó, không
  viết test của component, hook hay route.
- **Cấm viết unit test bừa bãi.** Không thêm unit test "cho đủ bao phủ", không một test cho mỗi hàm, không test lặp lại
  điều e2e đã kiểm, không test của mã chỉ chạm tới qua UI. Unit test chỉ cho các thứ **UI không thấy được**:
  - luật bảo mật và vai trò (T1–T9), luật harness (H1–H11), kiểm quyền, kiểm audit;
  - cấu trúc DB, migration, ràng buộc;
  - động cơ (ca, hàng đợi, khóa), và quy tắc thuần có đầu vào/ra rõ (parser, tính toán, quy tắc gửi).
- **Mỗi mô-đun tối đa 2 test unit: một ca chạy đúng, một ca bị từ chối hoặc lỗi.** Chọn hai ca đáng giá nhất; thêm ca thứ ba
  phải có lý do viết ngay trong test (một lỗi đã xảy ra thật, không phải "cho chắc").
- **Sửa lỗi:** thêm đúng một test cho lỗi đó nếu nó thuộc nhóm UI không thấy được; nếu UI thấy được thì thêm vào spec e2e.
- **Không tự xóa test có sẵn** chỉ vì luật này; test giữ luật T1–T9 và H1–H11 giữ nguyên trừ khi chủ nói khác. Việc rút
  gọn test cũ là việc chủ yêu cầu riêng.
- Test e2e chạy cần stack đang chạy (cấu hình và biến môi trường trong `frontend/e2e/playwright.config.ts`, đăng nhập trong `session.ts`); không tự dựng lại
  Docker hay đụng DB demo `pema` để chạy chúng, và chỉ chạy khi chủ bảo.
- Cuối báo cáo của task có code mới, ghi một dòng: test nào đã viết (e2e hay unit) và vì sao, hoặc "không viết test" kèm lý do.
