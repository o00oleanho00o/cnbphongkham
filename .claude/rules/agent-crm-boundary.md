# Ranh giới agent ↔ CRM — luật bất biến

Áp cho mọi thay đổi trong `pema-agent/` (backend `apps/agent`, `apps/api`, `infra/`), kể cả do subagent làm. Agent nói chuyện với
người ngoài (Zalo, chat web) nên **coi như có ngày bị jailbreak**: khi đó nó chỉ được phá trong vùng của nó.

- **L1. Agent không đọc ghi được DB của CRM.** Agent dùng database riêng `pema_agent`; role `agent_rt_app` không có CONNECT vào
  `pema` và không có USAGE trên schema nào ngoài `agent_rt`, `public`. Không cài `dblink`, `postgres_fdw`. Không bảng nào của app
  này đọc bảng của app kia.
- **L2. Agent không gọi được API của CRM.** Agent không giữ khóa, mật khẩu hay tài khoản dịch vụ nào của API. Nối duy nhất là agent
  tải khóa công khai (JWKS) để kiểm token SSO. API không bao giờ nhận token có `aud = pema-agent` làm phiên.
- **L3. Không có "cửa sổ cho agent" bên CRM.** Không schema, view, hàm SQL hay role riêng cho agent trong database `pema`.
- **L4. Dữ liệu phòng khám vào agent chỉ theo một đường:** nhân viên tải tài liệu đã duyệt lên kho tri thức. Không tool nào của
  agent tra bệnh nhân, lịch hẹn, đơn, tài chính.
- **L5. Muốn mở đường mới thì chủ hệ thống quyết**, bằng văn bản trong kế hoạch riêng; đường mới phải hẹp, chỉ đọc, có nhân viên
  duyệt. Không tự thêm vì "tiện".

Test giữ luật, đỏ là không merge: `apps/agent/tests/test_crm_boundary.py` (T1 db, T4), `apps/api/tests/api/test_agent_token.py`
(T3), `apps/api/tests/test_database.py` (T2 db). Khi thêm plugin, tool hay biến môi trường cho agent, chạy lại chúng.

Kế hoạch gốc: `pema-agent/docs/PLAN-db-baseline.md`.
