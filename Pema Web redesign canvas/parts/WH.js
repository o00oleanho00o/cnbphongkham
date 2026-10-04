// WH · Hỏi Pema (Ask Pema) và Hướng dẫn (guide). Filled by W3b-WH from design-specs/web/screens/WH1..WH14.md.
// The 11 guide articles are UI content of the old web (prototype/shared/guide.js) and stay verbatim; names in the Ask answer are
// canvas sample data. Everything lives in one function so the helper names cannot clash with another group part.
const WH = (() => {
  const ART = {
    "mobile-finance": { id: "mobile-finance", role: "Tất cả", title: "Mobile, CSKH & tài chính theo vai trò", summary: "Một hệ thống, các không gian làm việc rõ ràng.",
      why: "Tài chính nay nằm trong cùng khung Clinic. Mobile ưu tiên việc tiếp theo và thông tin của đúng người bệnh.",
      steps: [
        "Chủ hoặc kế toán chọn Tài chính & tiền thủ thuật ở sidebar; bác sĩ dùng Doanh số của tôi. Vai trò lấy từ tài khoản trên đầu trang.",
        "Patient Mobile → Hồ sơ → Nhóm tài khoản mẫu để chọn một trong 10 tình huống D1/D3/D7, tái khám, vắng hẹn, gián đoạn, 90/180 ngày và sinh nhật. Về Trang chủ để xem bước tiếp theo.",
        "App mobile: chọn không gian ở thanh trên. CSKH có ba trạng thái công việc, tìm kiếm và nút Lọc mở nhóm chăm sóc; chạm khách để ghi kết quả hoặc bàn giao bác sĩ.",
        "App mobile Care → Hồ sơ đổi người bệnh; Clinic/Care giữ lựa chọn riêng. Mỗi hồ sơ có lịch, giỏ và phản hồi riêng trong phiên."
      ],
      handoff: "Ghi chú CSKH và bàn giao là nội bộ; chỉ phản hồi được gửi mới đến người bệnh. CRM trên app mobile là bản mẫu độc lập web, chưa đồng bộ dữ liệu lâm sàng; tài chính PB02 dùng chung API. Bộ chọn tài khoản chưa phải xác thực production.",
      links: [["CSKH hôm nay"], ["Tài chính"]], related: ["crm01", "care", "billing"] },
    "crm01": { id: "crm01", role: "CSKH", title: "CSKH chủ động & tài khoản nhân viên", summary: "Đúng người, đúng việc, đúng mốc chăm sóc.",
      why: "Chọn tài khoản demo trên thanh đầu trang. Chủ phòng khám xem toàn cảnh, bác sĩ xem lịch/hồ sơ phụ trách, CSKH xử lý hàng đợi, kế toán làm việc ở thu ngân. Patient 360 nối bối cảnh, không ghép mọi tác vụ vào cùng dashboard.",
      steps: [
        "Chọn Mai Anh hoặc Thu để vào CSKH hôm nay. Lọc lý do, người phụ trách và hạn xử lý.",
        "Mở task, đọc lịch sử, liệu trình còn lại và ngày dự kiến quay lại trước khi gọi.",
        "Ghi kênh mô phỏng, kết quả, ghi chú và bước tiếp theo. Không nghe máy/bận cần giờ gọi lại.",
        "Đồng ý đặt lịch: tiếp tục form đã điền đúng hồ sơ, xử lý xung đột rồi lưu. Chưa lưu lịch thì chưa hoàn tất task.",
        "Phản hồi cần chuyên môn/khiếu nại được chuyển sang Theo dõi, bác sĩ phải xem.",
        "Chủ phòng khám xem số task, tỷ lệ liên hệ và lịch đặt sau CSKH; chỉ check-in mới tính quay lại thực tế."
      ],
      handoff: "CRM ghi kết quả nội bộ, không tự gửi lời khuyên y khoa. Kênh Zalo/SMS/cuộc gọi đang mô phỏng; tài khoản demo không phải đăng nhập bảo mật.",
      links: [["CSKH hôm nay"], ["Patient 360"], ["Điều phối lịch"]], related: ["records", "care", "schedule"] },
    "system": { id: "system", role: "Tất cả", title: "Hiểu hệ thống Pema", summary: "Một hồ sơ xuyên suốt, nhiều điểm tiếp nối chăm sóc.",
      why: "Patient 360 là nơi nối các sự kiện của một người bệnh. Lịch hẹn tổ chức lần gặp; buổi điều trị ghi nhận việc đã làm; chăm sóc tại nhà và phản hồi giúp đội ngũ chuẩn bị cho lần gặp tiếp theo.",
      steps: [
        "Tìm hồ sơ trước khi tạo mới để tránh chia lịch sử chăm sóc thành nhiều hồ sơ.",
        "Đọc kế hoạch, mốc gần nhất và việc còn mở trước khi quyết định bước tiếp theo.",
        "Thực hiện công việc ở màn phụ trách: điều phối ở Lịch, ghi chuyên môn ở Patient 360, phản hồi ở Theo dõi, thanh toán ở Thu ngân.",
        "Sau khi lưu, kiểm tra kết quả ở hồ sơ và phần thông tin người bệnh nhìn thấy."
      ],
      handoff: "Mỗi lần bàn giao cần rõ: ai phụ trách, việc nào đã hoàn tất và bước tiếp theo là gì. Có lịch hẹn không có nghĩa đã điều trị; đã thu tiền không có nghĩa đã hoàn tất chăm sóc.",
      links: [["Tìm hồ sơ"], ["Xem lịch"]], related: ["schedule", "clinical", "care", "billing"] },
    "roles": { id: "roles", role: "Tất cả", title: "Bắt đầu theo vai trò", summary: "Biết nơi bắt đầu và người nhận bàn giao tiếp theo.",
      why: "Mỗi bộ phận làm việc trên cùng hành trình người bệnh, với mục tiêu và điểm kiểm tra riêng.",
      steps: [
        "Lễ tân: tìm đúng hồ sơ → xếp lịch phù hợp → xác nhận hoặc check-in khi người bệnh đến.",
        "Bác sĩ: mở Patient 360 → xem lịch sử, cảnh báo, ảnh và phản hồi → ghi nhận, duyệt kế hoạch và hướng dẫn.",
        "Điều dưỡng / chăm sóc: theo dõi ảnh và cập nhật cần xử lý → chuyển bác sĩ xem khi cần → kiểm tra nội dung đã được phản hồi.",
        "Thu ngân: kiểm tra đúng người bệnh, đúng hóa đơn → thu tiền → kiểm tra số còn lại và phiếu thu.",
        "Người điều phối: xem tải bác sĩ/phòng → xử lý khoảng khóa → sắp lại lịch trước khi thay đổi khả năng phục vụ."
      ],
      handoff: "Đây là hướng dẫn phân công công việc; phiên bản hiện tại phân vai bằng tài khoản demo, chưa có xác thực và phân quyền server.",
      links: [["Hàng đợi hôm nay"], ["Bác sĩ & phòng"]], related: ["records", "schedule", "billing"] },
    "records": { id: "records", role: "Bác sĩ", title: "Hồ sơ & Patient 360", summary: "Đọc bối cảnh trước khi ghi thêm một sự kiện.",
      why: "Danh sách bệnh nhân giúp tìm đúng người; Patient 360 giúp hiểu người đó đang ở đâu trong quá trình chăm sóc.",
      steps: [
        "Vào Tìm bệnh nhân, tìm bằng tên, mã hồ sơ hoặc số điện thoại. Dùng bộ lọc để xem hồ sơ đang điều trị, có cảnh báo hoặc có hẹn.",
        "Bấm Mở để kiểm tra thông tin nhận diện, bác sĩ phụ trách, cảnh báo và lịch hẹn tiếp theo.",
        "Ở Tổng quan, đọc các mốc theo thời gian và thông tin cần nhớ; đối chiếu ảnh khi cần.",
        "Chuyển sang Tư vấn, Kế hoạch, Buổi điều trị hoặc Ảnh trước / sau theo công việc.",
        "Nếu cần hồ sơ mới, bấm Hồ sơ mới từ danh sách. Hồ sơ mới cần được khai thác tiền sử và thiết lập kế hoạch trước khi chăm sóc tiếp."
      ],
      handoff: "Lịch sử cho biết điều gì đã được ghi nhận và bởi ai. Tiến độ số buổi chỉ là số buổi hoàn tất, không phải tỷ lệ cải thiện da.",
      links: [["Mở danh sách bệnh nhân"]], related: ["clinical", "care", "schedule"] },
    "schedule": { id: "schedule", role: "Lễ tân", title: "Lịch hẹn & tiếp đón", summary: "Ghép đúng người bệnh, dịch vụ, bác sĩ, phòng và thời gian.",
      why: "Lịch hẹn là một cam kết sử dụng nguồn lực. Mỗi lịch cần đủ thời gian thực hiện và chuẩn bị phòng, đồng thời không trùng lịch khác.",
      steps: [
        "Vào Điều phối lịch. Chọn ngày hoặc 7 ngày, lọc bác sĩ/phòng để xem khả năng tiếp nhận.",
        "Bấm Đặt lịch hoặc Xếp lịch ở danh sách chờ. Chọn bệnh nhân, dịch vụ, bác sĩ, phòng, ngày và giờ.",
        "Dùng Tìm giờ trống nếu cần. Kiểm tra thời lượng, thời gian chuẩn bị và giá trước khi xác nhận.",
        "Muốn dời lịch: mở thẻ để sửa, hoặc kéo sang ô mới. Kéo thả chỉ điền vị trí mới vào form; bấm Lưu thay đổi mới ghi nhận.",
        "Mở thẻ để Xác nhận lịch. Khi người bệnh đến, dùng Check-in; không dùng check-in chỉ để xác nhận họ sẽ đến.",
        "Nếu hủy, nhập lý do. Lịch đã hủy không chiếm chỗ và được giữ trong lịch sử hồ sơ."
      ],
      handoff: "Sau khi lưu, lịch đã đặt xuất hiện trong Patient Mobile; lịch sắp tới trên hồ sơ được tính lại. Check-in của ngày hiện tại đưa người bệnh vào trạng thái đang chờ để bàn giao cho phòng khám.",
      rules: [
        "Trùng bác sĩ, người bệnh hoặc phòng: đổi giờ hoặc nguồn lực phù hợp.",
        "Khoảng chuẩn bị vẫn chiếm phòng; vùng gạch chéo không phải giờ trống.",
        "Ngoài ca, giờ nghỉ, phòng khóa hoặc dịch vụ tạm ngưng: cần chọn phương án khác."
      ],
      links: [["Mở điều phối lịch"], ["Mở tiếp đón"]], related: ["resources", "records", "clinical"] },
    "resources": { id: "resources", role: "Điều phối", title: "Bác sĩ, phòng & dịch vụ", summary: "Thiết lập điều kiện để lịch có thể thực hiện được.",
      why: "Thời lượng dịch vụ, phòng phù hợp và ca bác sĩ là đầu vào của điều phối. Điều chỉnh các điều kiện này cần tính tới những lịch đã cam kết.",
      steps: [
        "Vào Bác sĩ & phòng, chọn ngày để xem số lịch và số phút điều trị của từng bác sĩ.",
        "Bấm Xem lịch bác sĩ để chuyển sang lịch đã lọc.",
        "Khi phòng cần bảo trì hoặc tạm không sử dụng, tạo khoảng khóa có ngày, giờ và lý do. Nếu đang vướng lịch, dời lịch trước rồi mới khóa.",
        "Gỡ khóa khi phòng có thể hoạt động trở lại.",
        "Vào Dịch vụ để sửa tên, giá, thời lượng, thời gian chuẩn bị hoặc tạm ngưng."
      ],
      handoff: "Thông số dịch vụ mới áp dụng cho lịch mới. Khi chỉ dời giờ/phòng, lịch cũ giữ thông số đã chốt; đổi dịch vụ trong lịch lấy thông số của dịch vụ mới.",
      rules: [
        "Hiện ca bác sĩ là ca cố định, chưa có màn chỉnh ca hoặc nghỉ phép.",
        "Khóa phòng là thao tác điều phối, không phải hủy tự động các lịch đã đặt."
      ],
      links: [["Mở bác sĩ & phòng"], ["Mở dịch vụ"]], related: ["schedule"] },
    "clinical": { id: "clinical", role: "Bác sĩ", title: "Từ tư vấn đến buổi điều trị", summary: "Biến một lần gặp thành bản ghi có thể tiếp tục sử dụng.",
      why: "Kế hoạch thể hiện hướng theo dõi. Buổi điều trị ghi lại đánh giá, việc đã thực hiện và hướng dẫn cho giai đoạn ở nhà.",
      steps: [
        "Từ hồ sơ, xem tiền sử, cảnh báo, ảnh mốc và cập nhật chưa xử lý trước khi bắt đầu.",
        "Ở Tư vấn, nhập ghi chú. Nếu tạo bản nháp AI, đọc, chỉnh sửa rồi mới Duyệt & lưu vào Patient 360.",
        "Ở Kế hoạch, kiểm tra tên kế hoạch, tổng số buổi và số buổi đã hoàn tất. Điều chỉnh nếu cần.",
        "Ở Buổi điều trị, nhập ngày, đánh giá trước buổi và hướng dẫn sau buổi. Nếu gắn ảnh, kiểm tra đồng ý ảnh và thông tin vùng/góc chụp.",
        "Lưu buổi điều trị, sau đó kiểm tra sự kiện mới trong hành trình và hướng dẫn đã chuyển sang Patient Mobile."
      ],
      handoff: "Buổi đã lưu nối vào lịch sử và cập nhật số buổi hoàn tất. Hướng dẫn sau buổi là đầu vào của chăm sóc tại nhà. Nếu thiếu ảnh mốc, đội ngũ có mục theo dõi để bổ sung.",
      rules: [
        "AI brief và ghi chú cần bác sĩ xem, sửa và duyệt; không tự ra chẩn đoán.",
        "Ảnh và số buổi cần được đọc trong bối cảnh; không dùng làm kết luận tự động về hiệu quả."
      ],
      links: [["Chọn hồ sơ để làm việc"], ["Mở ảnh trước / sau"]], related: ["records", "care"] },
    "care": { id: "care", role: "Chăm sóc", title: "Chăm sóc & phản hồi tại nhà", summary: "Khép kín vòng phản hồi giữa người bệnh và phòng khám.",
      why: "Hành trình không kết thúc khi người bệnh rời phòng khám. Hướng dẫn và phản hồi giúp đội ngũ biết cần xem điều gì trước buổi tiếp theo.",
      steps: [
        "Người bệnh mở Chăm sóc tại nhà để đọc hướng dẫn đã gửi và xác nhận đã đọc.",
        "Người bệnh dùng Gửi cập nhật để mô tả tình trạng; có thể thêm ảnh và phải đồng ý cho sử dụng ảnh khi đính kèm.",
        "Đội ngũ vào Theo dõi để xem các mục đang mở và người phụ trách; ưu tiên phản hồi cần bác sĩ xem.",
        "Mở mục theo dõi, xem nội dung/ảnh, chỉnh phản hồi rồi Duyệt, phản hồi & đóng mục.",
        "Kiểm tra phản hồi trong tin nhắn người bệnh và sự kiện tương ứng ở Patient 360."
      ],
      handoff: "Gửi cập nhật tạo việc cần xử lý. Duyệt và phản hồi mới hoàn tất vòng theo dõi; gửi thành công không đồng nghĩa bác sĩ đã xem.",
      rules: [
        "Tin nhắn không phải kênh cấp cứu.",
        "CRM01 tự lập task D1/D3/D7 cho session có protocol Laser CO2. Nhân viên xử lý; không tự gửi tin hoặc tự review lâm sàng."
      ],
      links: [["Mở theo dõi"]], related: ["clinical", "records", "schedule"] },
    "billing": { id: "billing", role: "Thu ngân", title: "Hóa đơn & thu tiền", summary: "Phân biệt khoản phải thu, tiền đã nhận và trạng thái chăm sóc.",
      why: "Thanh toán gắn với hóa đơn của người bệnh. Dữ liệu thu tiền giúp các bộ phận thống nhất số còn lại mà không suy diễn trạng thái điều trị.",
      steps: [
        "Vào Thu ngân, chọn Tất cả, Còn phải thu hoặc Đã thanh toán. Dùng phân trang để xem thêm.",
        "Đối chiếu người bệnh, mã hóa đơn, dịch vụ, tổng tiền và số đã thu.",
        "Bấm Thu tiền, nhập số tiền thực nhận và chọn phương thức. Có thể thu một phần.",
        "Xác nhận, rồi kiểm tra phiếu thu và số còn lại. Hóa đơn đủ tiền chuyển sang Đã thanh toán.",
        "Người bệnh xem trạng thái tương ứng tại Hồ sơ → Tài liệu & hóa đơn."
      ],
      handoff: "Thu tiền cập nhật hóa đơn và phiếu thu. Thao tác này không tự đánh dấu một buổi điều trị hoàn tất và không thay đổi kế hoạch chuyên môn.",
      rules: [
        "Số tiền phải dương và không vượt dư nợ; hóa đơn đã đủ không nhận thu thêm.",
        "Hiện đặt lịch chưa tự tạo hóa đơn; chưa có phát hành hóa đơn mới, hoàn tiền hoặc kết nối ngân hàng."
      ],
      links: [["Mở thu ngân"]], related: ["records", "clinical"] },
    "exceptions": { id: "exceptions", role: "Tất cả", title: "Khi cần kiểm tra lại", summary: "Xử lý lỗi và hiểu phạm vi đang sử dụng.",
      why: "Khi hệ thống từ chối một thao tác, hãy đọc lý do và điều chỉnh dữ liệu đầu vào; không coi thông báo lỗi là đã lưu thành công.",
      steps: [
        "Lịch bị trùng: xem bác sĩ, phòng, người bệnh và khoảng chuẩn bị; chọn giờ khác hoặc dùng Tìm giờ trống.",
        "Không thể khóa phòng: kiểm tra lịch đã có trong khoảng đó và dời trước.",
        "Không lưu được: giữ bản nháp, kiểm tra thông báo và thử lại. Không lặp thao tác thu tiền khi chưa kiểm tra phiếu thu.",
        "Hai ứng dụng chưa khớp: mở Clinic Web và Patient Mobile trên cùng địa chỉ máy chủ và cùng hồ sơ trình duyệt; tải lại để kiểm tra."
      ],
      handoff: "Bản hiện tại phục vụ thử nghiệm nội bộ với dữ liệu giả lập, lưu trong trình duyệt. Chưa có đăng nhập/phân quyền thực, đồng bộ nhiều thiết bị, AI thật, SMS/Zalo, thanh toán hoặc vận hành sản xuất. Không nhập hồ sơ người bệnh thật.",
      links: [], related: ["schedule", "billing", "care"] }
  };
  // Order of the topic index (the `articles` order in guide.js).
  const ORDER = ['mobile-finance', 'crm01', 'system', 'roles', 'records', 'schedule', 'resources', 'clinical', 'care', 'billing', 'exceptions'];
  const CARE_MAP = [['01', 'Hồ sơ'], ['02', 'Lịch hẹn'], ['03', 'Điều trị'], ['04', 'Chăm sóc'], ['05', 'Tái khám']];
  const GUIDE_SEARCH = 'Ví dụ: dời lịch, bác sĩ, thu tiền';

  // Left column: search field and the topic list. Each topic button reads "role title" (the old buttons stack the small role over the
  // bold title); the open topic is the selected one.
  const topicIndex = (cur, q) => stack({ g: 14 },
    search(GUIDE_SEARCH, { label: 'Tìm chủ đề hoặc vai trò', val: q || '', suf: q ? 'close' : undefined }),
    q ? notice('Không tìm thấy. Thử “lịch”, “thu tiền” hoặc tên vai trò.', 'info')
      : chips(ORDER.map(id => [ART[id].role + ' ' + ART[id].title, id === cur ? 'sel' : '']), { vert: true }));

  // Right column: the article. Steps, handoff notice ("Thông tin đi tiếp như thế nào?"), "Điểm cần nhớ", action buttons, "Đọc tiếp".
  const article = id => {
    const a = ART[id];
    return card({ g: 18 },
      h2(a.title, a.summary, { eyebrow: a.role }),
      id === 'system' && grid(5, CARE_MAP.map(([n, name]) => secondary(n + ' ' + name + ' →', { full: true }))),
      grid('repeat(auto-fit,minmax(min(100%,520px),1fr))',
        stack({ g: 12 }, txt(a.why), h3('Cách thực hiện'), list(a.steps, { plain: true, ordered: true })),
        // The old aside (handoff, "Điểm cần nhớ" and its bullets) is one notice block in the web DOM, so it is one notice here.
        notice('Thông tin đi tiếp như thế nào? ' + a.handoff + (a.rules ? ' Điểm cần nhớ ' + a.rules.join(' ') : ''), 'info')),
      a.links.length > 0 && row({ g: 8 }, a.links.map(([l]) => primary(l + ' →'))),
      hr(),
      h3('Đọc tiếp'),
      row({ g: 8 }, a.related.map(r => secondary(ART[r].title + ' →'))));
  };

  const guidePage = (id, name, note, cur, o = {}) => page(id, name, WEB + note, 'guide', [
    pageHead('Hướng dẫn sử dụng', 'Hiểu hành trình, làm đúng bước và bàn giao đủ thông tin.', [], 'Cách làm việc cùng Pema'),
    grid('290px minmax(0,1fr)', topicIndex(cur, o.q), article(o.article || cur))
  ], o.state ? { state: true } : {});

  // Ask Pema: the query card on the left, the result card on the right.
  const ASK_PLACEHOLDER = 'Ví dụ: Ai quá hạn tái khám hơn 30 ngày?';
  const askPage = (id, name, note, o = {}) => page(id, name, WEB + note, 'ask', [
    pageHead('Ask Pema', 'Bộ truy vấn mô phỏng trên 46 hồ sơ tổng hợp · chưa tích hợp mô hình AI.', [secondary('Gợi ý câu hỏi')], 'Pema Digital Clinic'),
    grid('minmax(0,1.45fr) minmax(0,1fr)',
      panel('Bạn muốn biết điều gì?', 'Pema hiển thị nguồn dữ liệu và câu trả lời có thể kiểm tra lại.', [],
        row({ g: 12 }, ico('auto_awesome'), input('', o.q || '', { ph: ASK_PLACEHOLDER, w: 420 }), primary('Hỏi')),
        chips(['Ảnh chờ xem', 'Kế hoạch đang chạy', 'Quá hạn tái khám'])),
      o.answer
        ? card({ v: 'ai', eyebrow: 'Kết quả mô phỏng · có thể kiểm tra', title: o.q },
          txt('Có 2 ảnh chờ xem: ' + people[0].name + ' (' + people[0].id + '), ' + people[6].name + ' (' + people[6].id + '). Nguồn: Follow-up Inbox, status=open, có ảnh.', { size: 'b' }),
          secondary('Mở dữ liệu nguồn →'))
        : card({ v: 'ai', eyebrow: 'Kết quả sẽ xuất hiện ở đây', title: 'Ask Pema' },
          txt('Hãy hỏi một câu bên trái. Trong bản demo, câu trả lời luôn hiển thị cách tính và hồ sơ nguồn.')))
  ], o.state ? { state: true } : {});

  return [
    askPage('WH1', 'Ask Pema', 'ask · hai cột như web: ô hỏi và ba câu gợi ý bên trái, thẻ kết quả bên phải; app I12/F15 chỉ có một cột; tên và số liệu là dữ liệu tổng hợp'),
    askPage('WH2', 'Ask Pema · có câu trả lời', 'ask · sau khi hỏi "Ai có ảnh gửi sau laser đang chờ xem?": thẻ kết quả có câu trả lời, nguồn và nút "Mở dữ liệu nguồn →"; tên bệnh nhân là dữ liệu tổng hợp',
      { q: 'Ai có ảnh gửi sau laser đang chờ xem?', answer: true, state: true }),
    guidePage('WH3', 'Hướng dẫn sử dụng', 'guide · mục lục chủ đề bên trái, bài "Hiểu hệ thống Pema" bên phải với bản đồ 5 bước; app F16 là một cột 5 thẻ bàn giao; từ 1600px web chia bài thành hai cột (canvas: tự chia khi đủ rộng)', 'system'),
    guidePage('WH4', 'Hướng dẫn · Bắt đầu theo vai trò', 'guide · bài "roles": đoạn dẫn, 5 bước, ghi chú bàn giao và nút liên kết', 'roles', { state: true }),
    guidePage('WH5', 'Hướng dẫn · Hồ sơ & Patient 360', 'guide · bài "records"', 'records', { state: true }),
    guidePage('WH6', 'Hướng dẫn · Lịch hẹn & tiếp đón', 'guide · bài "schedule" có thêm "Điểm cần nhớ"', 'schedule', { state: true }),
    guidePage('WH7', 'Hướng dẫn · Bác sĩ, phòng & dịch vụ', 'guide · bài "resources"', 'resources', { state: true }),
    guidePage('WH8', 'Hướng dẫn · Từ tư vấn đến buổi điều trị', 'guide · bài "clinical": bản nháp AI cần bác sĩ duyệt', 'clinical', { state: true }),
    guidePage('WH9', 'Hướng dẫn · Chăm sóc & phản hồi tại nhà', 'guide · bài "care": tin nhắn không phải kênh cấp cứu', 'care', { state: true }),
    guidePage('WH10', 'Hướng dẫn · Hóa đơn & thu tiền', 'guide · bài "billing": thu tiền không tự đánh dấu buổi điều trị hoàn tất', 'billing', { state: true }),
    guidePage('WH11', 'Hướng dẫn · Khi cần kiểm tra lại', 'guide · bài "exceptions": không có nút điều hướng, chỉ có "Đọc tiếp"', 'exceptions', { state: true }),
    guidePage('WH12', 'Hướng dẫn · CSKH chủ động & tài khoản nhân viên', 'guide · bài "crm01"', 'crm01', { state: true }),
    guidePage('WH13', 'Hướng dẫn · Mobile, CSKH & tài chính theo vai trò', 'guide · bài "mobile-finance"', 'mobile-finance', { state: true }),
    guidePage('WH14', 'Hướng dẫn · không tìm thấy chủ đề', 'guide · gõ "zzzz" vào ô tìm: mục lục chỉ còn ghi chú "Không tìm thấy", bài mặc định vẫn hiển thị', 'system', { q: 'zzzz', state: true })
  ];
})();
