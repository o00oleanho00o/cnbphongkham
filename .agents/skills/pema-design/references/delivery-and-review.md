# Triển khai và bàn giao thiết kế

## Nguồn trong repository

| Việc | Nơi kiểm tra |
|---|---|
| Quyết định/acceptance/module/runtime | `docs/SCOPE-PB01.md` → `SPEC-PB01.md` → `MODULEMAP-PB01.md` → `ARCH-PB01.md` |
| Web style/asset | `prototype/shared/design.css`, `workspace-layout.css`, `styles.css`, CSS theo module và `assets/` |
| Web behavior | `prototype/shared/clinic.js`, `patient.js`, `operations-*`, `order-*`, `data.js` |
| Flutter theme/navigation/screens | `flutter-template/lib/core/` (theme, router, widgets) + `lib/features/*/presentation/screens/` |
| Flutter state | `flutter-template/lib/features/*/presentation/providers/` (Riverpod) |
| Native build + giới hạn | `docs/21_NATIVE_RUNBOOK.md`, `22_NATIVE_PARITY_AND_VALIDATION.md` |
| Review frame | `prototype/native-review/index.html` |

Đọc thứ tự CSS thực sự được load trước khi override; tránh append rule chồng chéo chỉ để thắng specificity. Sửa source, không sửa compiled `prototype/native-preview/`. Font/logo hiện có đủ để bắt đầu, không bắt buộc dịch vụ sinh ảnh hoặc công cụ trả phí.

## Dữ liệu và mock

Dùng 46 bệnh nhân tổng hợp (36 nền + 10 nhóm CSKH) và catalog người dùng cung cấp; không nhập hồ sơ thật. Fixture cần đủ trạng thái và tên/note dài để lộ lỗi bố cục. Không giả số liệu/lịch sử đồng bộ khi dữ liệu đó chưa tồn tại.

Catalog: `data/danhsach.xlsx` → `prototype/import-product-catalog.py` → `prototype/shared/product-catalog.json` → copy bundle `flutter-template/assets/products.json`. Sau đổi catalog, kiểm importer `--check`, hash hai JSON, số lượng/loại theo workbook và acceptance bị ảnh hưởng. Không hardcode 115 như invariant vĩnh viễn khi workbook đã đổi hợp lệ.

## Chọn kiểm tra theo thay đổi

Server web: từ `prototype`, `python -m http.server 4173 --bind 127.0.0.1`; kiểm server hiện có trước khi chạy trùng. Dùng cùng origin/profile cho hai web app. Đọc dependencies của script khi chạy trên máy mới.

| Thay đổi | Kiểm tra phù hợp từ gốc repo |
|---|---|
| Desktop layout | `node prototype/review-desktop.cjs`; xem screenshot và overflow |
| Patient mobile UI | `node prototype/review-ui.cjs`, `node prototype/patient-smoke.cjs` |
| Nghiệp vụ liên thông | `node prototype/check-linked.cjs`, `node prototype/data-audit.cjs` |
| Lịch/dịch vụ/thu ngân | `node prototype/operations-test.cjs` |
| Catalog/đơn/in web | `python prototype/import-product-catalog.py --check`, `node prototype/product-catalog-test.cjs`, `node prototype/order-test.cjs`; đổi print thì thêm `python prototype/order-pdf-test.py` |
| Smoke web | `node prototype/smoke-final.cjs` khi thay đổi ảnh hưởng navigation/chung |
| Flutter Dart/assets | Trong `flutter-template`: `flutter analyze`, `flutter test --reporter expanded`, `./build-preview.ps1`; xem các màn bị ảnh hưởng |
| Chỉ docs/skill | Link/file tồn tại, đối chiếu source, frontmatter validator của môi trường nếu có, `git diff --check` |

Không chạy mọi suite cho mọi thay đổi nhỏ. Không dùng test PDF web để xác nhận native print, không dùng store test đơn/receipt để tuyên bố cách ly mọi dữ liệu. Sáu test Flutter ban đầu chỉ gồm store, bốn layout test và một thao tác catalog → review; đọc test source hiện tại trước báo coverage mới.

## Bàn giao có thể kiểm chứng

Báo ngắn: thay đổi gì và lý do, màn/luồng bị ảnh hưởng, kiểm tra thực sự đã chạy, screenshot/artifact, giới hạn còn mở. Ghi rõ phân tích, template duyệt, hay implementation hoàn chỉnh. Dấu tick chỉ cho việc đã làm; yêu thích thiết kế không tự chứng nhận auth/payment/clinical safety.

Theo quy tắc dự án, khi thay đổi scope/hành vi cập nhật 0→1→2→3, sau đó README/tài liệu nghiệp vụ/UI/runbook/parity và append SECTION_PROGRESS. Khi chính quy ước thiết kế đổi, cập nhật skill tương ứng. Giữ lịch sử test đúng ngày và kênh.

Nếu người dùng yêu cầu commit/push: xem diff, stage rõ file thuộc nhiệm vụ (kể cả docs liên quan), bỏ log/cache/artifact không liên quan, kiểm staged diff và push nhánh được chọn; xác minh remote SHA. Không tạo commit/push chỉ vì skill có hướng dẫn này.


## Ngoại lệ tài chính PB02

Tổng quan chủ phòng khám, thu/đối soát và tiền thủ thuật mới dùng API/SQLite chung web/Flutter. Giữ phân biệt doanh số, thực thu, công nợ và tiền bác sĩ; snapshot tỷ lệ, kỳ chốt, projection theo role và thông báo foreground. Đọc `docs/24_FINANCE_AND_PROCEDURE_FEES.md` và bộ PB02 trước khi sửa; giới hạn finance memory-only ở PB01 không áp cho module mới. Chạy `python prototype/finance_test.py` khi thay công thức/ledger.


Thay đổi hiển thị trên web (màn, tab, modal, dialog, trường, nút, trạng thái, luồng, câu ràng buộc, token CSS) phải kèm một mục trong "Chờ chuyển" của `.claude/skills/pema-web-to-canvas/web-changes.md` cùng commit, để design canvas claude.ai/design được cập nhật đúng chỗ mà không phải rà lại toàn bộ màn. Chi tiết và mẫu ghi ở `AGENT.md` › "Ghi nhận thay đổi web cho design canvas".


Mobile CRM02: dùng `docs/25_MOBILE_CRM_AND_UNIFIED_FINANCE.md` làm nguồn hiện trạng. Tài chính nằm trong Clinic shell; native chọn role trước tác vụ, không nhét CSKH/thu ngân/clinical chung home. Care ưu tiên một bước tiếp theo; nội bộ và bàn giao không thành tin nhắn người bệnh.
