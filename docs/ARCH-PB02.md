# Architecture PB02

Web :4173 và Flutter → JSON HTTP :4174 → SQLite local. Server bind 127.0.0.1 mặc định; CORS chỉ loopback origin. API có transaction, unique payment IDs, role check và audit; role do client chọn phục vụ demo, không phải authentication production. Database nằm trong `.local/` bị git-ignore. Thời gian kế toán theo ngày Việt Nam; lọc tháng theo ngày nghiệp vụ.

Entities: service rate/version, completed procedure + performers snapshots, invoice, payment idempotency, monthly settlement snapshot, notifications + read state, audit. API state projection chỉ trả dữ liệu đúng role. CSV escape formula. Ghi tiền dùng transaction, không vượt dư nợ; receipt và notification commit cùng transaction. Legacy web import là ledger mirror, không thu tiền lần hai.

Native dùng http client có timeout/error/retry và poll khi foreground; không WebView. API base cấu hình bằng dart-define PEMA_FINANCE_API để dùng emulator/device trong mạng phát triển; không expose server public. Production cần auth/session/TLS, phân quyền tenant, migration/backup, outbox + FCM/APNs, reconciliation và test thiết bị thật trước dùng tiền thật.


## Mobile và Clinic shell — 22/09/2026

Finance mount(root) đóng polling và bỏ response cũ khi unmount, selector giới hạn root, role lấy từ PemaStaff duy nhất. /finance chuyển query sang /clinic-web/?screen=finance. Seed bổ sung có marker phiên bản, ID tránh va chạm; dữ liệu hiện có giữ nguyên. Mobile ensure CRM trước render với guard event. Flutter state theo patient trong memory, riêng selection Care/Clinic; phân vai UI là mô phỏng, chưa auth server.
