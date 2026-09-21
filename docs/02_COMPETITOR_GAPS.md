# Competitor teardown và khoảng trống

## Cách đọc
So sánh theo việc nhân viên phải hoàn tất trong ca làm, không đếm số module. Vendor claims được dẫn trực tiếp. Review aggregators bị chặn, nhưng Apple public RSS cung cấp các sample review có ngày; các sample không chứng minh prevalence hoặc chất lượng toàn vendor.

| Hệ thống | Điểm nên học/copy | Khoảng trống cần kiểm chứng tại Pema |
|---|---|---|
| ModMed | Specialty workflow; AI action có citation và approval ([AI](https://www.modmed.com/ai/)). | Không biết độ phù hợp workflow thẩm mỹ nhiều buổi, ảnh và aftercare Việt Nam nếu chưa trial. |
| Aesthetic Record | Photo/video, chart sign-off, patient portal, reminders, eRx ([clinical](https://www.aestheticrecord.com/features/clinical-solutions/)). | Breadth có thể khiến ownership follow-up bị phân tán; cần test từ session đến patient-submitted photo. |
| Pabau | Client portal, forms/charting, post/pre-care, before/after, unified conversations, scribe ([features](https://pabau.com/features/)). | Đã có nhiều parity; Pema phải thắng ở ngữ cảnh local, timeline rõ, ít click và quy tắc ảnh riêng. |
| VISIA | Imaging protocol và repeatable capture ([VISIA](https://www.canfieldsci.com/imaging-systems/visia-complexion-analysis/)). | Thiết bị/phòng chụp là workflow riêng; V1 cần metadata và consent, không cần rebuild imaging hardware. |
| VTTech | [Clinic overview](https://vttechsolution.com/phan-mem-phong-kham) quảng bá booking đến after-care, records, prescriptions, services/revenue và integrations; [Customer App](https://vttechsolution.com/app-khach-hang) có booking, treatment history, direct clinic connection, images/service/loyalty information và care/appointment notifications. | Chưa có independent VTTech complaint; public pages chưa đủ xác minh timeline/photo protocol/review ownership. Shadowing/trial để phân biệt feature thiếu với cấu hình/training/workflow fit. |

## Tại sao hệ thống chuyên nghiệp vẫn bị xem là “thiếu”
1. **Danh mục ≠ ngữ cảnh**: chart có note nhưng không chỉ ra việc cần làm hôm nay.
2. **Photo silo**: album thiếu body area/view/protocol/consent nên so sánh không đáng tin.
3. **Session không tạo hậu quả**: hoàn tất treatment không tự sinh aftercare, deadline và người phụ trách.
4. **Portal tách khỏi clinic queue**: bệnh nhân gửi ảnh nhưng không có SLA/review state.
5. **AI không có nguồn**: summary nghe hợp lý nhưng bác sĩ phải tìm lại toàn chart.
6. **Local fit**: ngôn ngữ, Zalo, quy trình thu cọc/đổi lịch và cách gọi liệu trình khác nhau.
7. **Quá nhiều bước**: receptionist né màn hình nếu mất nhiều click hơn chat/paper.
8. **Triển khai/đào tạo**: feature tồn tại nhưng không được cấu hình thành routine.

Đây là hypotheses, không phải kết luận chất lượng vendor. Pema discovery phải đo từng điểm bằng observed task time và artifact.

## Complaint evidence (public App Store RSS)

Public reviews support the mechanism behind “looks complete, feels missing”: users report slow/disjointed charting, difficult portal login, missing mobile parity, freezes/crashes, and support delays. They do **not** prove a vendor-wide defect.

- Aesthetic Record EMR RSS: https://itunes.apple.com/us/rss/customerreviews/id=1228049519/sortBy=mostRecent/json
- PatientNow RSS: https://itunes.apple.com/us/rss/customerreviews/id=1483512201/sortBy=mostRecent/json
- Pema should convert these themes into local tests: time-to-open chart, time-to-check-in, patient self-service recovery, upload photo without crash, and staff completion without switching device.
