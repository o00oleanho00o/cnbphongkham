# Nhận diện và hệ thị giác Pema

Baseline tổng hợp từ vòng web và Flutter ngày 22/09/2026; đây là quy ước thiết kế dự án, không tuyên bố là brand manual chính thức. Khi token/code thay đổi có chủ ý, cập nhật reference này cùng docs UI.

## Màu và tương phản

| Token | Giá trị | Vai trò |
|---|---|---|
| Primary | #0B4F94 | CTA chính, active navigation, liên kết có nhấn |
| Navy | #083A6E | Vùng nhận diện đậm, tiêu đề nhấn |
| Sky | #3CAAE5 | Chi tiết đồ họa, highlight nhẹ; không mặc định làm nền chữ trắng nhỏ |
| Ink | #17324D | Nội dung chính |
| Muted | #5D7184 | Metadata/chú thích vẫn đọc được |
| Paper | #F4F8FB | Nền app |
| Surface | #FFFFFF | Form, hồ sơ, nội dung cần tập trung |

Màu trạng thái success/warning/error lấy semantic token/component hiện có sau khi kiểm tra contrast; không tự dùng xanh thương hiệu cho mọi status. Nhãn chữ/icon phải phân biệt trạng thái ngay cả khi không nhìn màu. Đo contrast trên nền thực tế: mục tiêu WCAG AA 4.5:1 cho chữ thường, 3:1 cho chữ lớn; kiểm focus và control boundaries. Không ghi “đạt accessibility” chỉ vì dùng Material.

Phân cấp: nền nhạt → surface trắng → chữ rõ → một hành động nổi bật. Hạn chế gradient, shadow và badge cạnh tranh; tránh biến bảng lâm sàng thành dashboard marketing. Nhận diện có thể đậm ở hero, nhưng các hàng dữ liệu cần yên và dễ quét.

## Font, icon, spacing

- Be Vietnam Pro local cho tiếng Việt; regular/medium/semibold/bold. Không fallback Times/Georgia ở input/heading. Giữ giấy phép OFL và kiểm font thực sự load.
- Điểm bắt đầu cho native: body 14–16, label 12, heading khoảng 25 logical pixels; điều chỉnh theo hierarchy, không thu nhỏ chữ để nhét nội dung. Web desktop heading khoảng 30 khi phù hợp layout hiện có. Test tên tiếng Việt dài, giá tiền và ghi chú nhiều dòng.
- Spacing scale 4/8/12/16/20/24. Nhóm thông tin bằng proximity/alignment; không bọc mỗi label trong một card. Native card radius 18, hero 24, control theo theme hiện có (14); không áp mọi radius native lên web máy móc.
- Web dùng Lucide SVG đồng bộ (mốc 20px/stroke 1.7 trong hệ hiện tại); native dùng Material outlined. Không trộn emoji/Unicode ngẫu nhiên làm icon nghiệp vụ. Icon-only cần accessible name/tooltip khi phù hợp; icon trang trí không gây lặp nội dung đọc.
- Native touch target tối thiểu 48 logical pixels; check khoảng cách các nút, trạng thái disabled/loading và hit area thay vì chỉ kích thước nét icon.

## Logo, ảnh và nền

Asset gốc web ở `prototype/shared/assets/`: `pema-logo.png`, font `be-vietnam-pro-*`, `care-waves.svg`, icon/license Lucide. Flutter dùng `flutter-template/assets/` được khai báo trong pubspec. Tái sử dụng asset đã có, không nhân bản bộ thương hiệu mới trong skill.

Giữ tỷ lệ logo và khoảng thở; không kéo giãn, tô màu lại hoặc đặt logo lên nền tương phản kém. Wave xanh nhẹ chỉ ở hero/vùng nhận diện, tránh sau bảng, đơn thuốc hoặc ghi chú bác sĩ. Nền đẹp phải giúp tập trung, không che chữ hoặc tăng chiều dài home.

Ảnh bệnh nhân/Before–After giả lập phải có ngữ cảnh minh họa; không dùng ảnh AI như bằng chứng điều trị, không chấm điểm hiệu quả từ placeholder. Không đưa hồ sơ thật vào screenshot. Chỉ cần sinh ảnh khi asset hiện có không giải quyết được nhu cầu cụ thể; đây không phải bước bắt buộc.

Prompt ngắn gợi ý khi được yêu cầu ảnh nền: “Tạo nền trừu tượng cho Pema Clinic & Care: trắng và xanh #0B4F94/#3CAAE5, đường sóng mềm rất nhẹ, khoảng trống rộng cho chữ, sạch và điềm tĩnh; không chữ, không logo, không người, không hình ảnh kết quả điều trị; tỷ lệ [theo vị trí sử dụng].” Overlay chữ/logo bằng UI để giữ chất lượng và responsive.

## Khi tham khảo thiết kế khác

Ghi vấn đề đang giải quyết → pattern hữu ích → điều chỉnh cho Pema → cách kiểm tra. Không sao chép thương hiệu Annam/Fastboy. “Sở hữu vòng đời khách hàng” được chuyển thành mạch chăm sóc có bàn giao, không tự biến app thành công cụ quảng cáo hoặc thêm loyalty chưa được yêu cầu.

Nguồn định hướng đã dùng trong dự án: https://pema.vn/ ; https://github.com/Dammyjay93/interface-design ; https://github.com/vercel-labs/agent-skills . Không cần fetch lại các nguồn này cho mọi thay đổi nhỏ; source/token và quyết định được duyệt trong repo là baseline thực thi.
