# Module Map PB02

Móng: API JSON + SQLite transaction → actor demo/role guards → invoice/payment và import ledger → service-rate snapshots → procedure performers/approval → monthly settlement → notification inbox → web/Flutter projections.

Source: `prototype/finance_server.py` (API/store); `prototype/finance/` (workspace kế toán/chủ); `prototype/shared/finance-bridge.js` (cashier legacy sync); `flutter-template/lib/finance.dart` (app tài chính). Tránh thay localStorage các module lâm sàng ngoài scope. Test API và UI riêng, dùng database tạm cho unit/integration tests.


## Mobile và Clinic shell — 22/09/2026

Tái dùng finance.js dưới dạng mount/dispose, CSS giới hạn trong finance-workspace; Clinic làm shell duy nhất. crm-data bổ sung fixtures và projection patientNext; patient.js chọn nhóm/tài khoản. Flutter provider chứa hồ sơ và state theo patient, Workspace chọn vai trò trước khi chọn tác vụ.
