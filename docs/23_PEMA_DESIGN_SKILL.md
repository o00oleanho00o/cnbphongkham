# Chia sẻ và sử dụng Pema Design

Skill nằm trong repo tại [`.agents/skills/pema-design/SKILL.md`](../.agents/skills/pema-design/SKILL.md). Bản này tổng hợp các quyết định thiết kế đã làm cùng chủ dự án: nhận diện Pema, tối ưu desktop 1920×1020, mobile theo tác vụ, Flutter Clinic/Care, nghiệp vụ liên kết và bằng chứng kiểm thử. Skill hướng dẫn tiếp tục thiết kế, không thay source hoặc brand manual chính thức.

## Đồng nghiệp dùng thế nào

**Làm cùng repository:** clone/pull nhánh chứa skill rồi mở project trong agent hỗ trợ `.agents/skills`. Gọi `$pema-design` khi thực hiện yêu cầu thiết kế. Khả năng tự phát hiện tùy công cụ/phiên; nếu chưa thấy, mở phiên mới hoặc yêu cầu agent đọc đường dẫn SKILL.md trực tiếp. Không cần cài thêm bộ font/ảnh trong skill: asset đã ở repository.

**Chia sẻ riêng:** copy nguyên thư mục `pema-design` gồm SKILL.md, agents và references; không gửi mỗi file SKILL.md vì sẽ thiếu hướng dẫn chi tiết. Với Codex có thể đặt bản copy trong thư mục skills của cấu hình người dùng (`$CODEX_HOME/skills`, hoặc `~/.codex/skills` nếu không đặt CODEX_HOME). Công cụ khác dùng vị trí skill do công cụ đó hỗ trợ, hoặc đọc SKILL.md và references trực tiếp. Nếu đã có bản cài cùng tên, đối chiếu trước khi thay thế.

Các reference dùng đường dẫn source tương đối theo gốc repo, không phụ thuộc ổ F: hoặc user Windows cụ thể. Bản rời vẫn có đủ nguyên tắc thiết kế; chạy app/test, đối chiếu khả năng thực tế và lấy asset cần repository Pema. Ưu tiên bản trong repo khi có khác biệt với bản copy cá nhân; chia sẻ commit SHA để đồng nghiệp biết phiên bản. Không đóng gói dữ liệu bệnh nhân, cache, SDK hay compiled preview vào skill.

## Prompt mẫu

**Review trước khi sửa:**

> Dùng $pema-design phân tích màn Patient 360 hiện tại: bố cục, font, icon, màu, khoảng cách và tác vụ chính ở 1920×1020 và 390×844. Nêu vấn đề có bằng chứng và plan sửa; chưa sửa code.

**Triển khai web:**

> Dùng $pema-design tối ưu màn lịch Clinic Web cho 1920×1020, giữ được xếp lịch theo bác sĩ/phòng, filter và trạng thái. Triển khai, kiểm tra thêm 1440/1280/1024/390, test nghiệp vụ bị ảnh hưởng và cập nhật tài liệu theo 0→1→2→3.

**Thiết kế Flutter để duyệt:**

> Dùng $pema-design chuyển luồng [tên luồng] sang Flutter Clinic/Care theo nhận diện hiện tại. Làm template tương tác để duyệt, giữ ý nghĩa nghiệp vụ nhưng tối ưu cho điện thoại. Nêu rõ state thực, mô phỏng và khả năng chưa tích hợp; kiểm tra màn nhỏ và nội dung dài.

**Ảnh nền:**

> Dùng $pema-design xem hero Care có cần ảnh nền mới không. Ưu tiên asset hiện có; nếu cần, viết prompt ngắn tạo nền phù hợp Pema, không ảnh bệnh nhân hay kết quả điều trị, rồi đề xuất cách đặt chữ và logo.

## Nội dung của skill

| File | Dùng khi |
|---|---|
| [SKILL.md](../.agents/skills/pema-design/SKILL.md) | Chọn workflow, giữ quyết định cốt lõi |
| [Visual system](../.agents/skills/pema-design/references/visual-system.md) | Màu, font, icon, spacing, logo, wave/ảnh và nguồn tham khảo |
| [Screens & flows](../.agents/skills/pema-design/references/screens-and-flows.md) | Navigation, Patient 360, dịch vụ/đơn/lịch/thu ngân/follow-up và parity |
| [Platform layout](../.agents/skills/pema-design/references/platform-layout.md) | Responsive desktop, mobile web, Flutter, review screenshot |
| [Delivery & review](../.agents/skills/pema-design/references/delivery-and-review.md) | Source map, dữ liệu, chọn test và bàn giao |

## Duy trì

Đây là skill riêng của dự án; không áp cứng cho thương hiệu khác. Các giới hạn Flutter mô tả snapshot hiện tại để tránh hứa quá mức, không cấm phát triển tiếp. Khi nền dữ liệu, navigation hoặc token đổi, cập nhật code/docs và reference tương ứng trong cùng thay đổi. Không gọi test lịch sử là test vừa chạy; không coi skill tự cấp quyền commit/push hoặc publish.

Kiểm tra khi sửa skill: frontmatter/name, links tài liệu, đường dẫn source, loại bỏ placeholder chưa hoàn thiện; nếu môi trường có `skill-creator`, chạy `scripts/quick_validate.py` của skill đó với đường dẫn thư mục `pema-design`. Validator chỉ kiểm cấu trúc; vẫn phải đối chiếu lời hướng dẫn với code và thử trên công việc thật để đánh giá chất lượng thiết kế.
