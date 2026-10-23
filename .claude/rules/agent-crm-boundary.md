# Ranh giới agent ↔ CRM — luật bất biến

Áp cho mọi thay đổi trong `pema-agent/` (backend `apps/agent`, `apps/api`, `apps/crm-signer`, `infra/`), kể cả do subagent
làm. Agent nói chuyện với người ngoài (Zalo, chat web) nên **coi như có ngày bị jailbreak**: khi đó nó chỉ được phá trong vùng
của nó, và chỉ cho người đang chat với nó.

- **L1. Agent không đọc ghi được DB của CRM.** Agent dùng database riêng `pema_agent`; role `agent_rt_app` không có CONNECT vào
  `pema` và không có USAGE trên schema nào ngoài `agent_rt`, `public`. Không cài `dblink`, `postgres_fdw`. Không bảng nào của app
  này đọc bảng của app kia.
- **L2. Tiến trình agent không giữ khóa, mật khẩu hay tài khoản nào của CRM.** Mọi yêu cầu agent gửi tới CRM đi qua
  `crm-signer`, dịch vụ duy nhất giữ khóa riêng: nó chỉ nhận đúng 8 route của `/api/v1/agent-gateway` và ký cho mỗi yêu cầu
  một JWT Ed25519 sống ngắn với đúng một quyền `agent.*` của route đó. CRM chỉ giữ khóa công khai
  (`PEMA_AGENT_GATEWAY_PUBLIC_KEYS`; không đặt thì cổng trả 404) và chỉ mở nhóm route đó cho sáu quyền `agent.*`, không vai trò
  nhân viên nào có chúng. API không bao giờ nhận token `aud = pema-agent` làm phiên. Chiều ngược lại: CRM ký sự kiện bằng khóa
  riêng của CRM (`aud = pema-agent-events`) và chỉ gửi tới **một** route của agent (`/v1/hooks/crm/events`); route đó chỉ nhận,
  không trả dữ liệu, và token sự kiện không bao giờ mở được phiên của agent (plugin `sso` từ chối `aud` đó). Agent tải khóa
  công khai của CRM (JWKS) để kiểm token SSO và sự kiện; ngoài JWKS, profile agent chỉ giữ địa chỉ của `crm-signer`.
- **L3. Không có "cửa sổ cho agent" bên CRM.** Không schema, view, hàm SQL hay role riêng cho agent trong database `pema`.
  `clinic.patient_channel` (mối nối kênh chat → bệnh nhân) và `clinic.agent_event` (outbox sự kiện) là dữ liệu CRM; agent chỉ
  chạm chúng gián tiếp qua cổng và sự kiện ở L2.
- **L4. Dữ liệu phòng khám vào agent theo bốn đường, không hơn:** tài liệu nhân viên đã duyệt trong kho tri thức; danh sách giờ
  trống (không tên người); lịch sắp tới **của chính người đang chat**, kèm tối đa 3 lịch khác của người đó đổi trong 7
  ngày (đã đến, đang khám, đã khám, đã hủy, không đến), chỉ mã, giờ, thời lượng, trạng thái, không lý do hủy, không
  ghi chú (chủ duyệt 2026-10-21); sự kiện lịch của người đã nối (mã lịch, kênh, ID trên
  kênh, giờ, thời lượng, trạng thái, phiên bản, đồng ý nhận nhắc, ai đổi (người, agent hay hệ thống) và lúc đổi; không
  tên, số điện thoại, bác sĩ hay ghi chú). Agent ghi vào
  CRM đúng ba thứ: hồ sơ liên hệ (họ tên, số, đồng ý nhận nhắc; lần sau không sửa hồ sơ), lịch mới, đổi trạng thái hay giờ của
  lịch thuộc người đang chat. Người là kênh và ID của cuộc chat do mã gắn, model không chọn được; trong nhóm chat các tool lịch
  từ chối. Không tool nào tra bệnh nhân khác, đơn, tài chính.
- **L5. Muốn mở đường mới thì chủ hệ thống quyết**, bằng văn bản trong kế hoạch riêng; đường mới phải hẹp và có giới hạn. Mở
  thêm endpoint, quyền, loại sự kiện hay trường dữ liệu nào cho agent là đổi kế hoạch. Không tự thêm vì "tiện". Đường hiện có:
  `pema-agent/docs/PLAN-crm-plugin.md` (chủ duyệt 2026-10-19/20).
- **L6. Tool ra internet chỉ là tool của lõi và chỉ đi qua `netguard`** (`agentcore.harness.tools.builtin.netguard`): chỉ
  http/https, chỉ nối tới địa chỉ công khai đã kiểm (không máy chủ này, không mạng riêng của stack, không `169.254.169.254`),
  mỗi lần chuyển hướng kiểm lại. Plugin không tự gọi ra internet cho model; plugin `crm` chỉ gọi `crm-signer` trong mạng của
  stack. Hạ tầng như gọi model, embedding không phải tool nên không thuộc luật này. Container agent chỉ đọc
  (`read_only`, `cap_drop: [ALL]`, `no-new-privileges`), chỉ ghi `/data` và `/tmp`. Client HTTP của agent (model, embedding,
  TypeSafe, Zalo Bot) ra internet qua proxy `egress`, giai đoạn 1 chỉ ghi log mọi đích. **Chưa làm (bước 8 giai đoạn
  2):** agent chỉ ở mạng nội bộ, `web_*` và cầu nối Zalo cũng qua proxy, chỉ cho đích trong danh sách chủ duyệt.
- **L7. Danh sách tool và plugin của profile `clinic` là danh sách chủ đã duyệt.** Thêm tool, plugin, tiến trình con hay biến
  môi trường cho agent, hoặc bật `agent_writes`, là đổi kế hoạch, chủ duyệt. Không bao giờ có tool đọc file, chạy lệnh hay chạy mã trong tiến trình agent.

**Không còn test tự động cho L1–L7.** Chủ quyết (2026-10-23) bỏ hết unit test, kể cả T1–T9 (role agent không vào được
`pema`, token `aud = pema-agent` không mở phiên CRM, cổng chỉ nhận JWT của `crm-signer`, sáu quyền `agent.*` không vai trò
nào có, người A không đổi được lịch của người B, danh sách tool/plugin/biến môi trường của agent) và test của `crm-signer`
và của sự kiện. Các luật trên **vẫn bắt buộc**; không còn gì tự báo đỏ khi vi phạm, nên khi đụng tới plugin, tool, route
cổng, loại sự kiện, biến môi trường, role DB hay quyền thì tự đối chiếu với L1–L7 trước khi làm xong. Lịch sử các test: trong
git trước commit xóa test của ngày 2026-10-23.

Kế hoạch: `pema-agent/docs/PLAN-db-baseline.md` (L1–L5 gốc), `pema-agent/docs/PLAN-crm-plugin.md` (L2–L4, L6, L7 mục 3.8).
