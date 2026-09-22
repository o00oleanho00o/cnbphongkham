# Pema Digital Clinic — Software Specification PB01

Phạm vi là vertical slice Clinic Web ↔ Patient Mobile cho prototype và kế hoạch pilot.

## Acceptance cho native template (22/09/2026)

- Flutter widget tree chạy trên browser để duyệt, cùng asset/font/token nhận diện web.
- Clinic có 5 mục điều hướng; Care có 4 mục; Patient 360 mở màn con, back navigation và safe-area.
- Catalog 115 dòng, thiếu loại chặn duyệt; đơn nháp ẩn ở Care; chỉnh nháp không tạo thêm hóa đơn mẫu.
- Luồng gửi cập nhật → phản hồi và thu tiền mẫu có thay đổi trạng thái. Camera/PDF/AI/backend ghi rõ chưa tích hợp.
- Kiểm tra layout 360/390/430/768 logical pixels và widget exceptions; đây chưa phải nghiệm thu thiết bị thật.

## Vai trò và use case

| ID | Use case | Actor | Kết quả |
|---|---|---|---|
| UC-01 | Tiếp nhận và mở đúng hồ sơ | Lễ tân | Check-in gắn đúng patient và lịch |
| UC-02 | Đặt/dời/xác nhận lịch | Điều phối | Slot hợp lệ, không xung đột bác sĩ/phòng |
| UC-03 | Đọc/cập nhật Patient 360 | Bác sĩ | Ghi chú, cảnh báo, kế hoạch có lịch sử |
| UC-04 | Thêm dịch vụ và liệu trình | Bác sĩ/điều phối | Snapshot giá, buổi, hóa đơn chờ |
| UC-05 | Hoàn tất buổi điều trị | Bác sĩ/điều dưỡng | Session, aftercare, ảnh, follow-up và bước tiếp theo |
| UC-06 | Duyệt đơn thuốc | Bác sĩ | Draft → approved, mobile thấy đúng bản |
| UC-07 | Xử lý phản hồi/ảnh | Chăm sóc/bác sĩ | Follow-up có owner, review và phản hồi |
| UC-08 | Thu tiền và phân bổ cọc | Thu ngân | Ledger không thu trùng, dư nợ đúng |
| UC-09 | Theo dõi hành trình trên mobile | Người bệnh | Thấy lịch, aftercare, đơn duyệt và gửi update |
| UC-10 | Kiểm tra bằng chứng | QA/quản lý | Smoke, operations, data, responsive và ảnh đạt |

## Yêu cầu chức năng

### Patient và timeline

- FR-01: Tìm patient theo tên, mã hồ sơ hoặc số điện thoại; kết quả đủ để tránh nhầm.
- FR-02: Patient 360 hiển thị timeline và panel liên kết trong vùng nội dung của từng tab.
- FR-03: Mutation ghi actor, thời điểm, loại sự kiện và patient/episode trong demo; pilot có audit server.
- FR-04: Không tạo hồ sơ mới nếu chưa tìm patient hiện có.

### Lịch và nguồn lực

- FR-05: Đặt lịch cần patient, dịch vụ, bác sĩ, phòng, ngày/giờ, duration và status.
- FR-06: Cảnh báo trùng bác sĩ/phòng/patient và tính buffer/room block trước khi lưu.
- FR-07: Có day/week view, waitlist, filter và planned/confirmed/arrived/in_progress/completed/cancelled/no_show.
- FR-08: Kéo thả chỉ điền form; thay đổi có hiệu lực sau khi Lưu.

### Dịch vụ, liệu trình, session

- FR-09: Add dịch vụ tạo patient service plan với agreed price, discount, total sessions và owner.
- FR-10: Giá chốt là snapshot; session completed mới tăng used sessions.
- FR-11: Session completed yêu cầu operator, procedure note, aftercare sent/declined, next step và ảnh nếu protocol yêu cầu.
- FR-12: Dịch vụ mới tạo pending invoice; invoice không tự hoàn tất vì đã đặt lịch.

### Đơn thuốc và AI có duyệt

- FR-13: Prescription draft lưu medication, dosage/instruction, frequency, duration và người tạo.
- FR-14: Chỉ bác sĩ duyệt; approved lưu reviewer/time/version và hiển thị trên mobile.
- FR-15: Draft, rejected hoặc revoked không hiển thị như hướng dẫn đang dùng trên mobile.
- FR-16: AI brief/clinical note có source event/record, nhãn mô phỏng và trạng thái cần bác sĩ review; không chẩn đoán.
- FR-27: Catalog Excel giữ mã, tên, đơn vị, loại, giá sau thuế và số dòng nguồn. Thuốc → PRESCRIPTION; loại khác có giá trị → CONSULTATION; loại trống → UNRESOLVED.
- FR-28: Đơn nhiều dòng lưu snapshot, số lượng nguyên 1–9999, cách dùng, ghi chú, bác sĩ và chẩn đoán/nội dung tư vấn. Đổi loại hoặc Không in cần lý do; Không in vẫn tính hóa đơn.
- FR-29: Nháp có thể sửa trước khi thu tiền; version cũ bị từ chối. Duyệt cần bác sĩ phụ trách, cách dùng cho từng dòng được in, nội dung tư vấn và không còn UNRESOLVED. Đơn duyệt không sửa tại chỗ; không tự coi là đã cấp thuốc.
- FR-30: Preview nhận diện tên người bệnh, in riêng/tất cả A5 dọc đen trắng, không bỏ dòng hoặc cắt hướng dẫn dài. Phiếu tư vấn dùng “sản phẩm”, “phiếu này”, “Bác sĩ tư vấn”. Mobile chỉ chiếu đơn approved, tách hai nhóm, ẩn NONE.

### Follow-up, media và consent

- FR-17: Mobile gửi text/ảnh; phải có consent trước khi lưu ảnh; item mới là new/unread.
- FR-18: Follow-up có severity, dueAt, owner, status và action log; gửi không đồng nghĩa đã được bác sĩ xem.
- FR-19: Bác sĩ/chăm sóc review, phản hồi, resolve; ảnh giữ event và consent.
- FR-20: Before/After chỉ hiển thị ảnh cùng body area/capture context; không efficacy score tự động.

### Thu ngân

- FR-21: Invoice có total, paid, deposit allocated, balance và pending/partial/paid.
- FR-22: Deposit là allocation riêng; thu phần còn lại chỉ nhận số dương không vượt balance.
- FR-23: Overpayment, duplicate submit, invoice paid và service không tồn tại bị từ chối.
- FR-24: Payment không đổi session, plan progress hoặc prescription status.

### Hướng dẫn và dữ liệu mẫu

- FR-25: Tab Hướng dẫn giải thích bàn giao theo hành trình, role và link màn thao tác.
- FR-26: Reset demo khôi phục fixture; không trộn dữ liệu thật hoặc gọi dịch vụ ngoài.

## Non-functional requirements

| Nhóm | Mục tiêu PB01 |
|---|---|
| Responsive | Không document horizontal overflow ở 1920×1020, 1440×900, 1280×720, 1024×768, 390×844 |
| Usability | Trạng thái, lỗi và bước tiếp theo bằng tiếng Việt; bảng/lịch tự cuộn trong vùng của nó |
| Performance demo | Route local và thao tác thông thường phản hồi dưới 500 ms trên máy kiểm thử |
| Data safety | Chỉ synthetic data; không ghi PII thật, token hoặc ảnh thật vào repo |
| Accessibility | Focus nhìn thấy, label/role cho control, contrast đọc được, tap target mobile đủ lớn |
| Reliability | Mutation lỗi không mất state; payment có guard và rollback demo |
| Traceability | Screenshot/test output trỏ được tới flow và commit; docs cập nhật cùng thay đổi |
| Clinical safety | Không autonomous diagnosis; AI/đơn thuốc cần bác sĩ duyệt |

## Acceptance criteria (Given / When / Then)

### AC-01 Reception → Patient 360

- Given patient P001 có appointment hôm nay, when lễ tân tìm và check-in, then lịch thành arrived và mở đúng Patient 360.
- Given hai bệnh nhân gần tên, when tìm kiếm, then mã hồ sơ/số điện thoại mask xuất hiện để chọn đúng.

### AC-02 Service → plan → appointment → session

- Given catalog có dịch vụ, when thêm vào P001 với giá chốt và 6 buổi, then plan lưu snapshot giá/discount, tạo pending invoice và hiện trong Patient 360.
- Given appointment thuộc plan, when session completed có operator/note/aftercare/next step, then used sessions tăng một, timeline thêm event và follow-up được tạo/cập nhật.
- Given appointment trùng bác sĩ/phòng, when lưu, then bị từ chối và không có bản ghi nửa chừng.

### AC-03 Prescription draft → approval → mobile

- Given bác sĩ tạo draft, when mở Patient Mobile, then draft không xuất hiện.
- Given bác sĩ approve, when người bệnh tải lại mobile cùng origin, then approved hiển thị tên thuốc, cách dùng, tần suất, thời gian và reviewer/time.
- Given user không phải bác sĩ, when cố approve, then bị từ chối và status giữ nguyên.

### AC-03b Excel → đơn hỗn hợp → tách phiếu

- Given workbook hiện tại có 115 sản phẩm, when tái tạo catalog, then có 30 thuốc, 78 sản phẩm tư vấn và 7 dòng cần phân loại; JS và JSON khớp workbook.
- Given một đơn gồm thuốc, mỹ phẩm, TPCN và dòng thiếu loại, when lưu nháp, then đủ mọi dòng, có hóa đơn liên kết nhưng chưa in/phát hành mobile. Dòng thiếu loại chặn duyệt.
- Given bác sĩ nhập hướng dẫn và phân loại có lý do, when duyệt, then hai nhóm xuất hiện trên app và nút in được mở. Reload không mất quantity, note hoặc giá snapshot.
- Given 5 sản phẩm tư vấn với hướng dẫn ngắn, when xuất PDF, then cả 5 và footer nằm trên một A5. Hướng dẫn dài/nhiều sản phẩm tự chảy qua trang, giữ đủ chữ và footer.
- Given lỗi ghi localStorage, số lượng sai, patient không tồn tại hoặc bản sửa stale, when lưu, then từ chối và không tạo đơn/hóa đơn dở dang.

### AC-04 Deposit → invoice → later payment

- Given invoice 10.000.000 và deposit 3.000.000, when thu thêm 7.000.000, then invoice paid, ledger giữ hai entry riêng, paid không vượt total.
- Given balance 2.000.000, when nhập 2.500.000 hoặc submit hai lần, then bị từ chối hoặc idempotent và balance không âm.

### AC-05 Patient update/photo → inbox → response

- Given mobile gửi text có consent ảnh, when Clinic mở Follow-up Inbox, then item new/unread có ảnh liên kết.
- Given bác sĩ phản hồi và resolve, when mobile tải lại, then người bệnh thấy phản hồi, item có reviewer/time và rời hàng chờ mở.
- Given không consent, when gửi ảnh, then ảnh không lưu và lý do rõ ràng.

### AC-06 Evidence

- Given server local đang chạy, when chạy linked, desktop, operations, smoke và data audit, then exit code 0, không page error và artifacts được ghi.

## Ngoại lệ

- Xung đột lịch: hiển thị resource/time conflict, giữ form để sửa, không tạo appointment.
- Thiếu dữ liệu khi complete session: chỉ rõ trường, giữ draft và không tăng tiến độ.
- Draft prescription không hợp lệ: nêu dòng thiếu; không phát hành mobile.
- Lỗi localStorage: cảnh báo demo, không giả vờ đã lưu; cho phép retry/reset có chủ ý.
- Hai app khác origin/profile: hướng dẫn mở cùng origin; không hứa đồng bộ.
- Follow-up khẩn: gắn severity/escalation và chuyển SOP gọi trực tiếp; chat không phải cấp cứu.

## Dữ liệu tổng hợp và kiểm thử

Mọi test dùng 36 patient giả lập P001… và dữ liệu tiếng Việt tạo deterministically. Không đưa tên, số điện thoại hoặc ảnh người thật vào fixture/screenshot.
