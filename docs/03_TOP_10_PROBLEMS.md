# Top 10 vấn đề cần giải quyết (hypothesis backlog)

1. Không biết “bệnh nhân này đang ở bước nào và bước tiếp theo là gì”.
2. Lịch sử chia giữa chart, ảnh, Zalo, giấy và bảng tính.
3. Treatment nhiều buổi thiếu episode/plan/session rõ ràng.
4. Ảnh trước-sau không đồng nhất vùng, góc, ánh sáng hoặc consent.
5. Bệnh nhân báo triệu chứng/ảnh nhưng không có queue người nhận và deadline.
6. Follow-up quá hạn không được phát hiện theo treatment protocol.
7. Note dài nhưng pre-visit không tóm tắt được thay đổi kể từ lần trước.
8. AI tạo text nhưng không trỏ về event và không có trạng thái bác sĩ duyệt.
9. Reception cần thao tác nhanh nhưng phải đi qua form lâm sàng nặng.
10. Owner thấy doanh thu/lượt khám nhưng không thấy chất lượng hành trình (ảnh thiếu, follow-up chưa xử lý, dropout).

## Cách kiểm chứng
Mỗi hypothesis phải gắn observation: số lần rời app; thời gian task; số trường thiếu; số handoff; và artifact thật (ẩn danh). Không biến danh sách này thành roadmap trước workshop.

## Prioritization evidence and measurement

| Problem cluster | Source signal | Pema task to observe | Candidate success measure |
|---|---|---|---|
| Fragmented context / slow charting | AR App Store review sample 2026-08-04; YouMed manual-record pain | Returning patient consultation | Doctor locates last session, photo and response in ≤30s (pilot target, not achieved claim) |
| Mobile parity / login friction | PatientNow 2024-01-04; APPatient RSS | Patient opens aftercare and sends update | Completion without staff help; no desktop fallback |
| Photo reliability | PocketEMA 2025-12-29 photo crash report | Capture and attach standardized image set | Upload success; required metadata completeness |
| Follow-up ownership | YouMed post-visit communication pain; product hypothesis | New update → triage → owner → response | Unassigned items; overdue hours; response SLA |
| Weak operational metrics | YouMed reporting burden | Owner reconstructs one weekly KPI | KPI traces to records; manual spreadsheet work avoided |

Sources are in [research/source registry](../research/sources.md) and [verified complaint notes](../research/complaint-notes/verified-complaints.md). Targets require baseline measurement and agreement with Pema; they are not external performance benchmarks.
