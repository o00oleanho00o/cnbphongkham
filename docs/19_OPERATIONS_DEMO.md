# Hướng dẫn sử dụng hệ thống Pema

Mở trong Clinic Web: [Hướng dẫn](http://127.0.0.1:4173/clinic-web/?screen=guide).

Tài liệu tổ chức theo hành trình và bàn giao giữa các bộ phận. Nội dung tương ứng với tab Hướng dẫn; nguồn nội dung ở `prototype/shared/guide.js`.

## Hiểu hệ thống Pema

**Vai trò:** Tất cả

Một hồ sơ xuyên suốt, nhiều điểm tiếp nối chăm sóc.

Patient 360 là nơi nối các sự kiện của một người bệnh. Lịch hẹn tổ chức lần gặp; buổi điều trị ghi nhận việc đã làm; chăm sóc tại nhà và phản hồi giúp đội ngũ chuẩn bị cho lần gặp tiếp theo.

### Cách thực hiện

1. Tìm hồ sơ trước khi tạo mới để tránh chia lịch sử chăm sóc thành nhiều hồ sơ.
2. Đọc kế hoạch, mốc gần nhất và việc còn mở trước khi quyết định bước tiếp theo.
3. Thực hiện công việc ở màn phụ trách: điều phối ở Lịch, ghi chuyên môn ở Patient 360, phản hồi ở Theo dõi, thanh toán ở Thu ngân.
4. Sau khi lưu, kiểm tra kết quả ở hồ sơ và phần thông tin người bệnh nhìn thấy.

### Thông tin đi tiếp

Mỗi lần bàn giao cần rõ: ai phụ trách, việc nào đã hoàn tất và bước tiếp theo là gì. Có lịch hẹn không có nghĩa đã điều trị; đã thu tiền không có nghĩa đã hoàn tất chăm sóc.

### Dịch vụ, liệu trình và thanh toán

Trong Patient 360, **danh mục dịch vụ** chỉ là giá tham khảo cho lịch mới. Khi người bệnh đăng ký, Pema tạo một **dịch vụ gắn hồ sơ** với số buổi, giá chốt, giảm giá, bác sĩ phụ trách và tiến độ đã dùng. Giá chốt không đổi khi danh mục được chỉnh sửa sau đó. Thêm dịch vụ mới đồng thời tạo hóa đơn chờ thu để Thu ngân theo dõi; đặt lịch không tự tăng số buổi, chỉ buổi điều trị được lưu mới cập nhật tiến độ.

Tiền cọc là khoản đã nhận và được phân bổ vào liệu trình. Khi thu phần còn lại, hệ thống không tính tiền cọc như một giao dịch mới. Số đã thu, số cọc đã phân bổ và số còn phải thu được hiển thị riêng để tránh thu trùng.

### Đơn thuốc

Đơn thuốc đi theo luồng **bản nháp → bác sĩ kiểm tra và duyệt → người bệnh xem trên Patient Mobile**. Bản nháp vẫn nằm trong Patient 360 để chỉnh sửa nhưng không xuất hiện trên app. Mỗi dòng thuốc lưu tên, cách dùng, tần suất và thời gian; lịch sử duyệt giữ người duyệt và thời điểm. Đơn thuốc đã duyệt, cấp phát và hóa đơn là các trạng thái riêng, không tự suy ra trạng thái này từ trạng thái kia.

**Đọc tiếp:** Lịch hẹn & tiếp đón · Từ tư vấn đến buổi điều trị · Chăm sóc & phản hồi tại nhà · Hóa đơn & thu tiền

## Bắt đầu theo vai trò

**Vai trò:** Tất cả

Biết nơi bắt đầu và người nhận bàn giao tiếp theo.

Mỗi bộ phận làm việc trên cùng hành trình người bệnh, với mục tiêu và điểm kiểm tra riêng.

### Cách thực hiện

1. Lễ tân: tìm đúng hồ sơ → xếp lịch phù hợp → xác nhận hoặc check-in khi người bệnh đến.
2. Bác sĩ: mở Patient 360 → xem lịch sử, cảnh báo, ảnh và phản hồi → ghi nhận, duyệt kế hoạch và hướng dẫn.
3. Điều dưỡng / chăm sóc: theo dõi ảnh và cập nhật cần xử lý → chuyển bác sĩ xem khi cần → kiểm tra nội dung đã được phản hồi.
4. Thu ngân: kiểm tra đúng người bệnh, đúng hóa đơn → thu tiền → kiểm tra số còn lại và phiếu thu.
5. Người điều phối: xem tải bác sĩ/phòng → xử lý khoảng khóa → sắp lại lịch trước khi thay đổi khả năng phục vụ.

### Thông tin đi tiếp

Đây là hướng dẫn phân công công việc; phiên bản hiện tại chưa áp dụng tài khoản và phân quyền theo vai trò.

**Đọc tiếp:** Hồ sơ & Patient 360 · Lịch hẹn & tiếp đón · Hóa đơn & thu tiền

## Hồ sơ & Patient 360

**Vai trò:** Bác sĩ

Đọc bối cảnh trước khi ghi thêm một sự kiện.

Danh sách bệnh nhân giúp tìm đúng người; Patient 360 giúp hiểu người đó đang ở đâu trong quá trình chăm sóc.

### Cách thực hiện

1. Vào Tìm bệnh nhân, tìm bằng tên, mã hồ sơ hoặc số điện thoại. Dùng bộ lọc để xem hồ sơ đang điều trị, có cảnh báo hoặc có hẹn.
2. Bấm Mở để kiểm tra thông tin nhận diện, bác sĩ phụ trách, cảnh báo và lịch hẹn tiếp theo.
3. Ở Tổng quan, đọc các mốc theo thời gian và thông tin cần nhớ; đối chiếu ảnh khi cần.
4. Chuyển sang Tư vấn, Kế hoạch, Buổi điều trị hoặc Ảnh trước / sau theo công việc.
5. Nếu cần hồ sơ mới, bấm Hồ sơ mới từ danh sách. Hồ sơ mới cần được khai thác tiền sử và thiết lập kế hoạch trước khi chăm sóc tiếp.

### Thông tin đi tiếp

Lịch sử cho biết điều gì đã được ghi nhận và bởi ai. Tiến độ số buổi chỉ là số buổi hoàn tất, không phải tỷ lệ cải thiện da.

**Đọc tiếp:** Từ tư vấn đến buổi điều trị · Chăm sóc & phản hồi tại nhà · Lịch hẹn & tiếp đón

## Lịch hẹn & tiếp đón

**Vai trò:** Lễ tân

Ghép đúng người bệnh, dịch vụ, bác sĩ, phòng và thời gian.

Lịch hẹn là một cam kết sử dụng nguồn lực. Mỗi lịch cần đủ thời gian thực hiện và chuẩn bị phòng, đồng thời không trùng lịch khác.

### Cách thực hiện

1. Vào Điều phối lịch. Chọn ngày hoặc 7 ngày, lọc bác sĩ/phòng để xem khả năng tiếp nhận.
2. Bấm Đặt lịch hoặc Xếp lịch ở danh sách chờ. Chọn bệnh nhân, dịch vụ, bác sĩ, phòng, ngày và giờ.
3. Dùng Tìm giờ trống nếu cần. Kiểm tra thời lượng, thời gian chuẩn bị và giá trước khi xác nhận.
4. Muốn dời lịch: mở thẻ để sửa, hoặc kéo sang ô mới. Kéo thả chỉ điền vị trí mới vào form; bấm Lưu thay đổi mới ghi nhận.
5. Mở thẻ để Xác nhận lịch. Khi người bệnh đến, dùng Check-in; không dùng check-in chỉ để xác nhận họ sẽ đến.
6. Nếu hủy, nhập lý do. Lịch đã hủy không chiếm chỗ và được giữ trong lịch sử hồ sơ.

### Thông tin đi tiếp

Sau khi lưu, lịch đã đặt xuất hiện trong Patient Mobile; lịch sắp tới trên hồ sơ được tính lại. Check-in của ngày hiện tại đưa người bệnh vào trạng thái đang chờ để bàn giao cho phòng khám.

### Điểm cần nhớ

- Trùng bác sĩ, người bệnh hoặc phòng: đổi giờ hoặc nguồn lực phù hợp.
- Khoảng chuẩn bị vẫn chiếm phòng; vùng gạch chéo không phải giờ trống.
- Ngoài ca, giờ nghỉ, phòng khóa hoặc dịch vụ tạm ngưng: cần chọn phương án khác.

**Đọc tiếp:** Bác sĩ, phòng & dịch vụ · Hồ sơ & Patient 360 · Từ tư vấn đến buổi điều trị

## Bác sĩ, phòng & dịch vụ

**Vai trò:** Điều phối

Thiết lập điều kiện để lịch có thể thực hiện được.

Thời lượng dịch vụ, phòng phù hợp và ca bác sĩ là đầu vào của điều phối. Điều chỉnh các điều kiện này cần tính tới những lịch đã cam kết.

### Cách thực hiện

1. Vào Bác sĩ & phòng, chọn ngày để xem số lịch và số phút điều trị của từng bác sĩ.
2. Bấm Xem lịch bác sĩ để chuyển sang lịch đã lọc.
3. Khi phòng cần bảo trì hoặc tạm không sử dụng, tạo khoảng khóa có ngày, giờ và lý do. Nếu đang vướng lịch, dời lịch trước rồi mới khóa.
4. Gỡ khóa khi phòng có thể hoạt động trở lại.
5. Vào Dịch vụ để sửa tên, giá, thời lượng, thời gian chuẩn bị hoặc tạm ngưng.

### Thông tin đi tiếp

Thông số dịch vụ mới áp dụng cho lịch mới. Khi chỉ dời giờ/phòng, lịch cũ giữ thông số đã chốt; đổi dịch vụ trong lịch lấy thông số của dịch vụ mới.

### Điểm cần nhớ

- Hiện ca bác sĩ là ca cố định, chưa có màn chỉnh ca hoặc nghỉ phép.
- Khóa phòng là thao tác điều phối, không phải hủy tự động các lịch đã đặt.

**Đọc tiếp:** Lịch hẹn & tiếp đón

## Từ tư vấn đến buổi điều trị

**Vai trò:** Bác sĩ

Biến một lần gặp thành bản ghi có thể tiếp tục sử dụng.

Kế hoạch thể hiện hướng theo dõi. Buổi điều trị ghi lại đánh giá, việc đã thực hiện và hướng dẫn cho giai đoạn ở nhà.

### Cách thực hiện

1. Từ hồ sơ, xem tiền sử, cảnh báo, ảnh mốc và cập nhật chưa xử lý trước khi bắt đầu.
2. Ở Tư vấn, nhập ghi chú. Nếu tạo bản nháp AI, đọc, chỉnh sửa rồi mới Duyệt & lưu vào Patient 360.
3. Ở Kế hoạch, kiểm tra tên kế hoạch, tổng số buổi và số buổi đã hoàn tất. Điều chỉnh nếu cần.
4. Ở Buổi điều trị, nhập ngày, đánh giá trước buổi và hướng dẫn sau buổi. Nếu gắn ảnh, kiểm tra đồng ý ảnh và thông tin vùng/góc chụp.
5. Lưu buổi điều trị, sau đó kiểm tra sự kiện mới trong hành trình và hướng dẫn đã chuyển sang Patient Mobile.

### Thông tin đi tiếp

Buổi đã lưu nối vào lịch sử và cập nhật số buổi hoàn tất. Hướng dẫn sau buổi là đầu vào của chăm sóc tại nhà. Nếu thiếu ảnh mốc, đội ngũ có mục theo dõi để bổ sung.

### Điểm cần nhớ

- AI brief và ghi chú cần bác sĩ xem, sửa và duyệt; không tự ra chẩn đoán.
- Ảnh và số buổi cần được đọc trong bối cảnh; không dùng làm kết luận tự động về hiệu quả.

**Đọc tiếp:** Hồ sơ & Patient 360 · Chăm sóc & phản hồi tại nhà

## Chăm sóc & phản hồi tại nhà

**Vai trò:** Chăm sóc

Khép kín vòng phản hồi giữa người bệnh và phòng khám.

Hành trình không kết thúc khi người bệnh rời phòng khám. Hướng dẫn và phản hồi giúp đội ngũ biết cần xem điều gì trước buổi tiếp theo.

### Cách thực hiện

1. Người bệnh mở Chăm sóc tại nhà để đọc hướng dẫn đã gửi và xác nhận đã đọc.
2. Người bệnh dùng Gửi cập nhật để mô tả tình trạng; có thể thêm ảnh và phải đồng ý cho sử dụng ảnh khi đính kèm.
3. Đội ngũ vào Theo dõi để xem các mục đang mở và người phụ trách; ưu tiên phản hồi cần bác sĩ xem.
4. Mở mục theo dõi, xem nội dung/ảnh, chỉnh phản hồi rồi Duyệt, phản hồi & đóng mục.
5. Kiểm tra phản hồi trong tin nhắn người bệnh và sự kiện tương ứng ở Patient 360.

### Thông tin đi tiếp

Gửi cập nhật tạo việc cần xử lý. Duyệt và phản hồi mới hoàn tất vòng theo dõi; gửi thành công không đồng nghĩa bác sĩ đã xem.

### Điểm cần nhớ

- Tin nhắn không phải kênh cấp cứu.
- D1/D3/D7 là định hướng tổ chức chăm sóc; phiên bản hiện tại chưa tự lập và gửi chuỗi nhắc này.

**Đọc tiếp:** Từ tư vấn đến buổi điều trị · Hồ sơ & Patient 360 · Lịch hẹn & tiếp đón

## Hóa đơn & thu tiền

**Vai trò:** Thu ngân

Phân biệt khoản phải thu, tiền đã nhận và trạng thái chăm sóc.

Thanh toán gắn với hóa đơn của người bệnh. Dữ liệu thu tiền giúp các bộ phận thống nhất số còn lại mà không suy diễn trạng thái điều trị.

### Cách thực hiện

1. Vào Thu ngân, chọn Tất cả, Còn phải thu hoặc Đã thanh toán. Dùng phân trang để xem thêm.
2. Đối chiếu người bệnh, mã hóa đơn, dịch vụ, tổng tiền và số đã thu.
3. Bấm Thu tiền, nhập số tiền thực nhận và chọn phương thức. Có thể thu một phần.
4. Xác nhận, rồi kiểm tra phiếu thu và số còn lại. Hóa đơn đủ tiền chuyển sang Đã thanh toán.
5. Người bệnh xem trạng thái tương ứng tại Hồ sơ → Tài liệu & hóa đơn.

### Thông tin đi tiếp

Thu tiền cập nhật hóa đơn và phiếu thu. Thao tác này không tự đánh dấu một buổi điều trị hoàn tất và không thay đổi kế hoạch chuyên môn.

### Điểm cần nhớ

- Số tiền phải dương và không vượt dư nợ; hóa đơn đã đủ không nhận thu thêm.
- Hiện đặt lịch chưa tự tạo hóa đơn; chưa có phát hành hóa đơn mới, hoàn tiền hoặc kết nối ngân hàng.

**Đọc tiếp:** Hồ sơ & Patient 360 · Từ tư vấn đến buổi điều trị

## Khi cần kiểm tra lại

**Vai trò:** Tất cả

Xử lý lỗi và hiểu phạm vi đang sử dụng.

Khi hệ thống từ chối một thao tác, hãy đọc lý do và điều chỉnh dữ liệu đầu vào; không coi thông báo lỗi là đã lưu thành công.

### Cách thực hiện

1. Lịch bị trùng: xem bác sĩ, phòng, người bệnh và khoảng chuẩn bị; chọn giờ khác hoặc dùng Tìm giờ trống.
2. Không thể khóa phòng: kiểm tra lịch đã có trong khoảng đó và dời trước.
3. Không lưu được: giữ bản nháp, kiểm tra thông báo và thử lại. Không lặp thao tác thu tiền khi chưa kiểm tra phiếu thu.
4. Hai ứng dụng chưa khớp: mở Clinic Web và Patient Mobile trên cùng địa chỉ máy chủ và cùng hồ sơ trình duyệt; tải lại để kiểm tra.

### Thông tin đi tiếp

Bản hiện tại phục vụ thử nghiệm nội bộ với dữ liệu giả lập, lưu trong trình duyệt. Chưa có đăng nhập/phân quyền thực, đồng bộ nhiều thiết bị, AI thật, SMS/Zalo, thanh toán hoặc vận hành sản xuất. Không nhập hồ sơ người bệnh thật.

**Đọc tiếp:** Lịch hẹn & tiếp đón · Hóa đơn & thu tiền · Chăm sóc & phản hồi tại nhà
