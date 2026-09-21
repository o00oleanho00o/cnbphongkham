# Nghiên cứu thị trường

> Snapshot công khai truy cập ngày 2026-09-20. Vendor copy mô tả khả năng; không xem là bằng chứng hiệu quả hay mức độ sử dụng tại Pema.

| Nhóm | Quan sát kiểm chứng được | Hàm ý Pema |
|---|---|---|
| Specialty EHR | [ModMed Dermatology](https://www.modmed.com/specialties/dermatology/) trình bày EHR chuyên khoa và AI assistants; trang AI nhấn mạnh output có nguồn và người dùng phê duyệt. | AI nên tạo brief/note có nguồn event, luôn có approve; bắt đầu từ công việc lặp lại. |
| Aesthetic EMR | [Aesthetic Record Clinical Solutions](https://www.aestheticrecord.com/features/clinical-solutions/) liệt kê before/after photo/video, chart sign-off/auditing, cloud eRx, clinical documentation, portal, texting. | Feature parity đã cao; wedge là liên kết ảnh–session–aftercare–follow-up, không phải copy checklist. |
| Clinic platform | [Pabau Features](https://pabau.com/features/) liệt kê calendar, portal, forms/charting, scribe, measurement-based care, postcare, before/after, letters/dictation, prescriptions, inbox/engagement. | Cần kiểm chứng thao tác thực tế, số click và ownership của follow-up. |
| Clinical photography | [Canfield VISIA](https://www.canfieldsci.com/imaging-systems/visia-complexion-analysis/) mô tả hệ thống imaging/analysis chuẩn hóa. | Lưu view/body area/date/protocol/consent; không biến ảnh thường thành chẩn đoán. |
| Practical AI | [Skin Analytics](https://www.skin-analytics.com/ai-for-dermatology/) thể hiện AI da liễu trong bối cảnh triển khai lâm sàng. [FDA AI-enabled device list](https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices) cho thấy AI y tế cần quản trị theo intended use. | V1 dùng workflow AI hỗ trợ, không tuyên bố diagnostic AI. |
| Việt Nam | [VTTech Clinic](https://vttechsolution.com/phan-mem-phong-kham) quảng bá hành trình từ booking đến after-care, records/appointments/prescriptions/services/revenue; [Customer App](https://vttechsolution.com/app-khach-hang) quảng bá booking, lịch sử điều trị, kết nối trực tiếp clinic, ảnh/dịch vụ/loyalty và care/appointment notifications; [YouMed](https://youmed.vn/tin-tuc/phan-mem-quan-ly-phong-kham/) mô tả pain reception, giấy/Excel và post-visit communication. | VTTech đã có độ phủ rộng và app; cần thắng ở specialty workflow continuity, không giả định vendor thiếu module. |

## Kết luận
Thị trường đã phủ lịch, chart, payments, ảnh và portal. Khoảng trống có giá trị là **context continuity**: một sự kiện điều trị phải sinh ra aftercare, nhắc follow-up, yêu cầu ảnh và hàng đợi người xử lý có deadline. Mỗi workflow cần event log để AI tóm tắt có kiểm chứng.

## Phản hồi App Store có thể kiểm chứng

Apple public RSS được truy cập ngày 20/09/2026 (review gần đây; đây là phản hồi tự chọn, không đại diện toàn bộ người dùng):

- **Aesthetic Record EMR** — [App Store](https://apps.apple.com/us/app/aesthetic-record-emr/id1228049519), track ID 1228049519. Một review 1★ (2026-08-04) mô tả charting “bloated and disjointed”, giao diện chậm, portal khó đăng nhập nếu bỏ lỡ email mời, và thiếu self-service reset; review 2★ (2026-07-29) nêu update làm charting chậm và support phản hồi chậm; review 1★ (2025-11-19) nêu search/navigation/reporting và crash. Đây là ý kiến người dùng, không phải fact đã kiểm định.
- **PatientNow** — [App Store](https://apps.apple.com/us/app/patientnow/id1483512201), track ID 1483512201. Review 2★ (2024-01-04) liệt kê app iPad thiếu đổi/xem invoice cũ, copy tài liệu, nhiều lịch và check-in realtime; review 1★/2★ khác nêu freeze, logout và app thiếu chức năng desktop.
- **Pabau GO** — [App Store](https://apps.apple.com/us/app/pabau-go/id1057335634), track ID 1057335634. RSS không trả review nội dung trong lần lấy mẫu; không suy đoán.

**Hàm ý trực tiếp cho Pema:** self-service login/recovery và tốc độ charting là workflow acceptance criteria; mobile không được là bản cắt chức năng khiến staff phải dùng desktop; mỗi update phải có smoke test cho chart, photo upload, schedule và patient check-in.

## Market segmentation and buy/integrate choices

- **PatientNow** publicly combines EMR, scheduling/payments, RxPhoto clinical before/afters, marketing and AI automation ([official home](https://www.patientnow.com/)). Copy the concept of photos as clinical context; do not recreate a payments stack.
- **Zenoti** publicly spans medspa charting, appointment book, membership/package, mobile, AI receptionist, operations and marketing ([official home](https://www.zenoti.com/)). Pema should avoid competing on generic salon/spa enterprise breadth; learn queue speed and channel handoffs.
- **Nextech** official site was 403 in this environment; exact App Store complaint samples are in the research note. Do not fill missing product-depth evidence from assumptions.

Buy or integrate e-invoice, payment rails, SMS/Zalo delivery and mature imaging devices. Build longitudinal care context, review ownership and configurable treatment protocol. Pilot success requires measurable task speed and patient follow-up completion, not feature count.

Review dates above use the date portion of Apple RSS `updated` ISO timestamp; timezone offsets remain in saved raw JSON.
