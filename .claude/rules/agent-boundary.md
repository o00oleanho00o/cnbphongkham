# Ranh giới của agent — luật bất biến

Áp cho mọi thay đổi trong repo này (backend `apps/agent`, `connectors/`, `infra/`), kể cả do subagent làm. Agent nói chuyện
với người ngoài (Zalo, chat web) nên **coi như có ngày bị jailbreak**: khi đó nó chỉ được phá trong vùng của nó, và chỉ cho
người đang chat với nó.

Contete Agent là sản phẩm riêng, không có CRM (tách khỏi dự án phòng khám ngày 2026-11-18; plugin `crm`, `sso` và dịch vụ
`crm-signer` đã bỏ hẳn ngày 2026-11-19). Số luật giữ nguyên như trước để các ghi chú trong code còn khớp; L2 và L3 là luật
của phần nối CRM nên không còn.

- **L1. Agent chỉ có database của nó.** Agent dùng database riêng `pema_agent`; role `agent_rt_app` không có CONNECT vào
  database nào khác và không có USAGE trên schema nào ngoài `agent_rt`, `public`. Không cài `dblink`, `postgres_fdw`.
- **L2, L3.** (Bỏ cùng CRM.) Tiến trình agent không giữ khóa, mật khẩu hay tài khoản của hệ thống nào khác.
- **L4. Dữ liệu vào agent theo một đường:** tài liệu nhân viên đã duyệt trong kho tri thức. Người đang chat là kênh và ID
  của cuộc chat do mã gắn, model không chọn được. Không tool nào tra người khác.
- **L5. Muốn mở đường mới thì chủ hệ thống quyết**, bằng văn bản trong kế hoạch riêng; đường mới phải hẹp và có giới hạn.
  Nối agent với một hệ thống ngoài (CRM, lịch, thanh toán…), mở thêm endpoint, quyền hay trường dữ liệu cho agent là đổi kế
  hoạch. Không tự thêm vì "tiện".
- **L6. Tool ra internet chỉ là tool của lõi và chỉ đi qua `netguard`** (`agentcore.harness.tools.builtin.netguard`): chỉ
  http/https, chỉ nối tới địa chỉ công khai đã kiểm (không máy chủ này, không mạng riêng của stack, không `169.254.169.254`),
  mỗi lần chuyển hướng kiểm lại. Plugin không tự gọi ra internet cho model. Hạ tầng như gọi model, embedding không phải
  tool nên không thuộc luật này. Container agent chỉ đọc (`read_only`, `cap_drop: [ALL]`, `no-new-privileges`), chỉ ghi
  `/data` và `/tmp`. Client HTTP của agent (model, embedding, TypeSafe) và của connector Zalo (Zalo Bot, cầu nối) ra
  internet qua proxy `egress`, giai đoạn 1 chỉ ghi log mọi đích.
  **Chưa làm (giai đoạn 2):** agent chỉ ở mạng nội bộ, `web_*` và connector cũng qua proxy, chỉ cho đích trong danh sách
  chủ duyệt.
- **L7. Danh sách tool và plugin của profile `rag` là danh sách chủ đã duyệt** (`web`, `knowledge`, `jev`, `skills`,
  `conversations`, `follow_up`, `connectors`; chủ duyệt 2026-11-18). Thêm tool, plugin, tiến trình con hay biến môi trường
  cho agent là đổi kế hoạch, chủ duyệt. Không bao giờ có tool đọc file, chạy lệnh hay chạy mã trong tiến trình agent.
  **Kênh chat ngoài (Zalo…) là connector, dịch vụ riêng ngoài agent** (`connectors/<tên>`, giao thức
  `docs/CONNECTOR-PROTOCOL.md`): agent chỉ có plugin `connectors` chung, không biết nền tảng nào; connector không có DB
  agent, chỉ có khóa riêng của nó do trang Connectors cấp (thu hồi được). Trang quản trị của connector chỉ mở cho đăng
  nhập dashboard của agent, do agent kiểm. Thêm connector mới là cấp khóa mới, không phải thêm tool; kênh của nó chịu L4
  như mọi kênh.

**Không có test tự động cho các luật này.** Chủ quyết (2026-10-23) bỏ hết unit test. Các luật **vẫn bắt buộc**; không còn
gì tự báo đỏ khi vi phạm, nên khi đụng tới plugin, tool, route, biến môi trường, role DB hay quyền thì tự đối chiếu với
L1–L7 trước khi làm xong.

Lịch sử: `docs/PLAN-db-baseline.md` và `docs/PLAN-crm-plugin.md` là kế hoạch của thời còn nối CRM (mục 3.8 và 3.10 của
PLAN-crm-plugin là gốc của L6, L7); phần CRM trong đó không còn áp dụng.
