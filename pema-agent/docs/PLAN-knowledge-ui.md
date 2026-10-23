# Plan: phần "Kho tri thức" của trang Điều khiển agent (nơi thêm và quản lý dữ liệu cho RAG)

Trạng thái: **đã duyệt 2026-10-12, đang dựng UI trên nhánh `feat/knowledge-ui`** (quyết định ở mục 10). Bổ sung cho [PLAN-knowledge-plugin.md](PLAN-knowledge-plugin.md)
(mục 9 của plan đó chỉ liệt kê 5 trang; tài liệu này thiết kế cụ thể cách NẠP và QUẢN LÝ dữ liệu). Làm cùng các bước của
plan RAG (bảng ở mục 9 dưới đây).

## 1. Tên và vị trí

- **Tên: "Kho tri thức"** (tab mới trong "Điều khiển agent": Tổng quan · Phiên chat · Trace · **Kho tri thức** · Model · Plugins).
  Lý do chọn "Kho tri thức" thay "Hiểu biết": đây là những tài liệu agent TRA CỨU; "Hiểu biết" để dành cho cả 5 tầng
  context engineering (nhân cách, kỹ năng, bộ nhớ, tài liệu, ngữ cảnh) làm sau, khi đó "Kho tri thức" trở thành một mục bên
  trong. Đổi tên chỉ là một dòng chữ.
- **Là plugin `knowledge`** (nửa trình duyệt `ui/dist/client.js` như Zalo), không phải code lõi của clinic web. Các
  trang viết MỘT lần bằng `sdk.ui` (kit) và `sdk.api`, nên chạy được cả trong clinic web (:3000) lẫn bảng quản trị riêng
  của agent (:8088).
- **Thêm vào SDK một khai báo nhỏ:** `Contribution.section?: { title: string; page: string }`. Khi plugin bật và đã đăng
  ký, layout "Điều khiển agent" thêm một tab "Kho tri thức" trỏ tới `/admin/agent/plugins/knowledge/sources` (sáng khi đường
  dẫn bắt đầu bằng `/admin/agent/plugins/knowledge`). Plugin tắt thì tab biến mất.
- **Một trang, nhiều tab bên trong** (đã làm vậy khi dựng UI): plugin đăng ký MỘT trang `store` ("Kho tri thức") tự giữ
  các tab Nguồn · Dịch vụ · Thử tìm · Câu hỏi chưa có tài liệu · Cài đặt và chi tiết một nguồn bằng trạng thái trong trang,
  không dùng `?source=`. Lý do: cùng một mã chạy ở clinic web (đường dẫn thật) và bảng riêng của agent (`#/p/...`), hai bên
  khác cách điều hướng; trạng thái trong trang thì giống nhau cả hai. Bù lại chưa có liên kết sâu tới một nguồn.

## 2. Người dùng làm gì → màn hình nào

| Việc | Màn hình |
|---|---|
| Thêm một tài liệu (file, hoặc gõ/dán văn bản) | Nguồn → "+ Thêm nguồn" |
| Thêm cả bộ tài liệu một lần (thư mục .md / zip) | Nguồn → "+ Thêm nguồn" → "Nhập hàng loạt" |
| Biết tài liệu đã nạp xong chưa, có lỗi gì | Nguồn (trạng thái, tiến độ) |
| Kiểm tra máy đã hiểu cấu trúc tài liệu đúng chưa, sửa trước khi nạp | Xem trước (bước giữa của luồng thêm) và Chi tiết nguồn |
| Cho bệnh nhân thấy một tài liệu / giữ nội bộ | Cờ "Đối tượng" của nguồn |
| Duyệt tài liệu trước khi bệnh nhân thấy | Nút "Duyệt" (hàng loạt được) |
| Thay giá cũ bằng bảng giá mới | "Thay thế nguồn cũ" khi thêm; hoặc Chi tiết → "Hết hiệu lực" |
| Dạy máy tên gọi khác của dịch vụ ("hori" = "bớt hori") | Dịch vụ |
| Xem agent sẽ tìm được gì cho một câu hỏi | Thử tìm |
| Biết khách hỏi gì mà chưa có tài liệu | Câu hỏi chưa có tài liệu |
| Chọn embedding, kiểm tra kết nối, nhúng lại | Cài đặt |

## 3. Các màn hình

Mọi màn hình dùng kit của dashboard (Card, Button, Field, Select, Badge, Notice, bảng, Sheet/Dialog), tiếng Việt, đủ trạng
thái rỗng/tải/lỗi, dùng được trên điện thoại (bảng thu gọn thành danh sách thẻ).

### 3.1 Nguồn (`sources`): trang chính

- Đầu trang: 4 số (Nguồn sẵn sàng · Đoạn · Đã nhúng vector (%) · Lỗi) và dải cảnh báo nếu có: "Embedding chưa kết nối: đang tìm
  bằng từ khóa", "N nguồn chưa duyệt", "N nguồn lỗi".
- Bảng: **Tên** (+ mã tài liệu `doc_id` nhỏ) · **Loại** (file/văn bản, định dạng) · **Dịch vụ** (chip) · **Đối tượng**
  (Bệnh nhân / Nội bộ) · **Trạng thái xử lý** (Chờ / Đang xử lý + thanh tiến độ "đã chia 42 đoạn · nhãn 18/42 · vector 0/42"
  / Sẵn sàng / Lỗi + lý do) · **Hiệu lực** (Đang dùng / Nháp / Đã thay thế / Hết hạn + ngày) · **Duyệt** · **Đoạn** · Cập nhật.
- Lọc: ô tìm (tên, mã tài liệu), trạng thái, đối tượng, dịch vụ, hiệu lực, "Chưa duyệt". Phân trang 30 dòng.
- Chọn nhiều dòng → thanh thao tác: Duyệt, Bỏ duyệt, Đặt đối tượng (Bệnh nhân / Nội bộ), Nạp lại, Xóa (hỏi lại, nói rõ
  "mất N đoạn; agent không còn dẫn chứng từ nguồn này").
- Tự làm mới 2 giây một lần khi có nguồn đang xử lý; ngừng khi hết.
- Nút "+ Thêm nguồn" (mục 3.2); liên kết "Thử tìm", "Dịch vụ", "Câu hỏi chưa có tài liệu", "Cài đặt".

### 3.2 Thêm nguồn: một luồng 3 bước trong Sheet (không rời trang)

**Bước 1 – Chọn cách thêm** (3 thẻ):
1. **Tải tệp**: kéo thả hoặc chọn nhiều tệp (`.md .txt .docx .xlsx .pdf`; ≤ 25 MB mỗi tệp). Hiện ngay cảnh báo sai định
   dạng hoặc quá nặng trước khi gửi.
2. **Gõ hoặc dán văn bản**: tiêu đề + nội dung (Markdown cũng được); dùng cho FAQ ngắn, chính sách; ≤ 100.000 ký tự.
3. **Nhập hàng loạt**: chọn thư mục chứa nhiều `.md` có phần đầu YAML (mục 4); nhập `.zip` để dành cho bước backend. Dành cho việc nạp cả bộ tài
   liệu một lần (bộ demo Pema 22 tệp, hay xuất từ nơi khác).

**Bước 2 – Thông tin** (mỗi tệp một dòng, sửa hàng loạt được):
- Tên hiển thị (mặc định tên tệp); **Đối tượng**: Nội bộ (mặc định, an toàn) hoặc Bệnh nhân; **Dịch vụ liên quan** (chọn
  trong danh mục, hoặc để "Tự nhận diện"); **Hiệu lực** từ ngày – đến ngày (mặc định từ hôm nay, không hạn); **Thay thế
  nguồn cũ** (chọn một nguồn đang dùng: nguồn cũ chuyển "Đã thay thế" cùng lúc nguồn mới sẵn sàng); ghi chú.
- Cờ "Cho phép nạp tài liệu thử thách (giá cũ, nháp, tấn công thử)" chỉ hiện ở chế độ benchmark (mục 4); tắt thì tài
  liệu có `ingest_role: challenge` bị từ chối với lý do rõ.

**Bước 3 – Xem trước (parse thử, chưa nhúng, chưa tốn tiền model)**:
- Máy đọc tệp và cho thấy **cây tiêu đề** đã dựng, số đoạn dự kiến, độ dài trung bình đoạn, bảng nào được tách hàng.
- **Cảnh báo cụ thể**, mỗi cái có cách xử lý: "Không tìm thấy tiêu đề nào (PDF mất định dạng?) → Dựng lại bằng AI /
  Chỉnh tay"; "PDF scan, chưa đọc được"; "Có số điện thoại / số CCCD / email trong văn bản" (cảnh báo, không chặn: kho
  không dành cho dữ liệu bệnh nhân); "Có N mục giống kịch bản nội bộ nhưng đối tượng đang là Bệnh nhân → đề nghị tách";
  "Trùng hệt với nguồn <tên> (cùng nội dung) → Bỏ qua / Cập nhật phiên bản"; "Trùng tên với nguồn <tên> → Thay thế?".
- Người dùng bấm **"Nạp N nguồn"** (hoặc sửa bản dựng rồi nạp). Từ đây chạy nền; Sheet đóng, bảng Nguồn hiện các dòng "Đang
  xử lý".
- Nếu parse lỗi: dòng đó báo lỗi bằng câu tiếng Việt đọc được, các tệp khác vẫn đi tiếp.

### 3.3 Chi tiết nguồn (`sources?source=<id>`)

Đầu trang: tên, trạng thái, đối tượng, hiệu lực, duyệt (ai, lúc nào); nút Nạp lại · Duyệt · Hết hiệu lực · Tải bản gốc · Xóa.
Ba tab:
- **Bản dựng cấu trúc**: Markdown đã dựng, sửa được trong ô soạn thảo (bên cạnh: cây tiêu đề). "Nạp lại từ bản này"; "Tách các
  mục đã chọn thành nguồn mới" (dùng cho cẩm nang trộn phần bệnh nhân và phần nội bộ; nguồn mới mặc định Nội bộ).
- **Đoạn**: danh sách đoạn (đường dẫn tiêu đề, nội dung, độ dài, có vector chưa), nhãn `dịch vụ` / `loại` sửa được từng
  đoạn, tìm trong đoạn; cảnh báo đoạn quá dài/ngắn; đoạn có nhãn `internal_script` được đánh dấu.
- **Lịch sử**: các phiên bản, ai tải, ai duyệt, lần nạp lại, lỗi từng lần; quay về phiên bản trước (tạo bản mới từ bản cũ).

### 3.4 Dịch vụ (`services`)

Bảng: mã, tên, tên gọi khác (chip, thêm/xóa nhanh), mô tả, chi nhánh (tùy chọn), số đoạn đang gắn, bật/tắt. "Nhập từ bảng"
(dán CSV/Markdown). Đây là "xương sống" cho nhãn và mở rộng truy vấn. Đổi tên gọi khác có hiệu lực ngay cho tìm kiếm (không
cần nhúng lại); đổi mã dịch vụ hỏi lại vì ảnh hưởng nhãn.

### 3.5 Thử tìm (`try`)

Ô câu hỏi + chọn "Như kênh bệnh nhân / Như nhân viên" + ngày hỏi (mặc định hôm nay) + phòng khám. Hiện từng tầng, mỗi tầng
một thẻ có thể mở: Hiểu câu hỏi (từ đã bỏ dấu, dịch vụ nhận ra) → ứng viên từ khóa (điểm) → ứng viên vector (khoảng cách) →
sau gộp RRF → sau xếp lại → gói cuối đúng như agent thấy (có `doc_id`, đường dẫn tiêu đề) và thời gian từng bước. Nút "Dùng
làm ca đo" thêm câu hỏi vào bộ đo (mục 8 plan RAG).

### 3.6 Câu hỏi chưa có tài liệu (`gaps`)

Danh sách câu agent đã tra mà không có kết quả đủ tốt (đã chuẩn hóa, đếm số lần, kênh, lần gần nhất). Mỗi dòng: "Viết câu
trả lời" mở luồng Thêm nguồn kiểu "Gõ văn bản" với tiêu đề điền sẵn từ câu hỏi; "Bỏ qua" (không phải việc của kho). Đây là
vòng phản hồi để kho tốt dần.

### 3.7 Cài đặt (`settings`)

- **Embedding**: nhà cung cấp (OpenAI-compatible: địa chỉ, khóa API cài đặt nhạy cảm mã hóa không hiện lại, model, số chiều
  1024, tiền tố câu hỏi/tài liệu). Nút **"Kiểm tra kết nối"**: gọi một lần, báo số chiều trả về, độ chuẩn hóa, thời gian, lỗi
  đọc được (chính là phép thử đã làm tay với Beeknoee). Trạng thái hiện hành: model đang dùng cho kho, số đoạn chưa có vector.
  Nút **"Nhúng lại toàn bộ"** (job nền, có thể hủy).
- **Đọc tài liệu**: parser (`docling` sidecar | `simple`), địa chỉ Docling, kiểm tra kết nối.
- **Gán nhãn và xếp lại** (dùng model chat đang chọn, có thể trỏ model khác trong danh sách), bật/tắt.
- **Tìm kiếm**: số kết quả, ngưỡng, ngân sách ký tự; kênh bệnh nhân (tiền tố kênh); "kênh bệnh nhân chỉ thấy nguồn đã duyệt".
- Mỗi cài đặt hiện nguồn giá trị (đã lưu / theo profile) và "Về mặc định", giống trang Model.

## 4. Nhập hàng loạt và phần đầu YAML (frontmatter)

Tài liệu `.md` có thể mang phần đầu YAML. Khi có, hệ thống đọc làm giá trị mặc định cho bước 2 (người dùng vẫn sửa được):

| Trường YAML | Vào đâu |
|---|---|
| `doc_id` | mã tài liệu dùng để TRÍCH DẪN (`kb_source.doc_code`), duy nhất trong phòng khám |
| `title` | tên hiển thị |
| `tenant_id` | phải khớp phòng khám của agent; khác thì từ chối dòng đó ("tài liệu của phòng khám X") |
| `version`, `status` (`active|draft|superseded|adversarial`) | `kb_source.version`, `lifecycle` |
| `effective_from`, `effective_to` | hiệu lực |
| `audience` (`patient|staff`) | Đối tượng |
| `ingest_role` (`kb|challenge`) | `challenge` chỉ nạp được khi bật chế độ benchmark, và không bao giờ vào kho thường |

- Zip: giải nén an toàn (không tuyệt đối/`..` trong đường dẫn, trần số tệp 200, trần dung lượng giải nén 100 MB, chỉ nhận
  `.md .txt .docx .xlsx .pdf`), mỗi tệp thành một dòng ở bước 2. Thư mục: trình duyệt gửi từng tệp.
- Cùng `doc_id` đã có: hỏi "Cập nhật phiên bản" (nguồn cũ giữ lịch sử) hay bỏ qua.
- Trong bước 3, các tài liệu cùng `doc_id` khác phiên bản/hiệu lực hiển thị gộp, để thấy ngay "giá cũ v1 (đến 30/09) và giá
  hiện hành (từ 01/10)".
- Chế độ benchmark là một cài đặt của plugin (mặc định tắt), dùng khi chạy bộ đo Mây/Pema. Bộ dữ liệu benchmark sống ngoài
  repo; hệ thống nhập từ đường dẫn người dùng chọn qua trình duyệt, không đọc đường dẫn máy chủ tùy ý.

## 5. API của plugin (`/v1/plugins/knowledge`, quyền admin; mọi route kiểm xác thực và quyền)

| Route | Việc |
|---|---|
| `GET /sources?q=&status=&audience=&service=&lifecycle=&approved=&page=` | danh sách + đếm tổng quan |
| `POST /sources/preview` (multipart: tệp, hoặc JSON văn bản) | parse thử, trả cây tiêu đề, số đoạn, cảnh báo, `preview_id` |
| `POST /sources/confirm` (`preview_id`, thông tin từng nguồn) | tạo nguồn, đưa vào hàng đợi nạp |
| `POST /sources/import` (zip) | giải nén an toàn, trả danh sách tệp + metadata đọc từ YAML để vào bước 2 |
| `GET /sources/{id}` · `PATCH /sources/{id}` (tên, đối tượng, hiệu lực, dịch vụ) · `DELETE` | chi tiết, sửa, xóa |
| `POST /sources/{id}/reindex` · `/approve` · `/unapprove` · `/expire` | nạp lại, duyệt, bỏ duyệt, hết hiệu lực |
| `GET/PUT /sources/{id}/structure` · `POST /sources/{id}/split` | bản dựng cấu trúc, tách mục thành nguồn mới |
| `GET /sources/{id}/chunks` · `PATCH /chunks/{id}` | đoạn, sửa nhãn |
| `GET /sources/{id}/events` | lịch sử |
| `GET/POST/PATCH/DELETE /services` | danh mục dịch vụ và tên gọi khác |
| `POST /search/debug` | Thử tìm theo từng tầng |
| `GET /gaps` · `PATCH /gaps/{id}` | câu hỏi chưa có tài liệu |
| `GET/PATCH /settings` · `POST /settings/test-embedding` · `POST /settings/reembed` | cài đặt, kiểm tra kết nối, nhúng lại |
| `GET /status` | số liệu đầu trang, hàng đợi, cảnh báo |

Giới hạn thân request: kiểm `limit_body` của gateway và proxy của clinic web (hiện chặn thân lớn); tải tệp lớn gửi từng tệp
một, không gộp nhiều tệp vào một request. Tải tệp lên không giữ tệp trong bộ nhớ lâu: ghi vào `ctx.data_dir`, tên tệp do hệ
thống đặt (không dùng tên người dùng làm đường dẫn).

## 6. Dữ liệu bổ sung so với plan RAG (mục 4.1)

- `kb_source` thêm: `doc_code` (mã trích dẫn), `version`, `lifecycle` (`active|draft|superseded|expired|adversarial`, **tách khỏi**
  `status` xử lý), `supersedes` (id nguồn bị thay), `content_hash`, `batch_id`, `preview_id` (tạm), `created_by`.
- `kb_import_batch` (id, người tạo, số tệp, kết quả) cho nhật ký nhập hàng loạt.
- `kb_source_event` (nguồn, loại sự kiện, người, lúc, ghi chú) cho tab Lịch sử.
- `kb_preview` (id, kết quả parse, hết hạn sau 1 giờ) để bước Xem trước không tạo nguồn thừa.
- Tìm kiếm luôn lọc theo `lifecycle = active` và ngày hỏi (mục 19 plan RAG); tài liệu `adversarial` chỉ vào qua chế độ benchmark.

## 7. An toàn và giới hạn

- Chỉ vai có quyền quản trị agent (owner, manager qua SSO). Mọi thao tác ghi (nạp, duyệt, xóa, sửa cài đặt) ghi vào
  `kb_source_event` kèm người thực hiện.
- Mặc định tài liệu mới là **Nội bộ** và **chưa duyệt**: không bệnh nhân nào thấy cho tới khi admin đổi và duyệt. Đổi một
  nguồn sang Bệnh nhân hiện hộp xác nhận liệt kê cảnh báo (mục nội bộ, số điện thoại).
- Tệp: kiểm chữ ký (magic bytes) chứ không tin đuôi tệp; trần dung lượng; zip bomb; parse trong tiến trình con có timeout
  và trần RAM; `.docx/.xlsx` đọc bằng SAX có trần; văn bản lọc ký tự ẩn (Unicode Tags).
- Khóa API embedding/Docling là cài đặt nhạy cảm: mã hóa, không trả lại, không vào log hay trace.
- Văn bản trong tài liệu hiển thị trên trang luôn là TEXT (không HTML), Markdown chỉ render bằng bộ render an toàn.
- Khối lượng: tối đa 5.000 nguồn và 200.000 đoạn mỗi phòng khám ở bản đầu (cảnh báo khi gần chạm).

## 8. Làm trong repo như thế nào

- Plugin: `apps/agent/plugins/knowledge/ui/` (vite + React như Zalo, kit từ `sdk.ui`); mỗi trang một tệp trong `ui/src/pages/`.
- Clinic web (`pema-agent/frontend`): chỉ đổi (a) `Contribution.section` trong `src/lib/agent/sdk.ts`, (b) layout "Điều khiển
  agent" đọc nó để thêm tab, (c) `mock/agent.ts` thêm các route giả của plugin (nguồn, preview, dịch vụ, tìm, cài đặt) để làm UI
  với `pnpm dev:mock` trước khi backend xong, (d) bản dựng `ui/dist/client.js` của plugin.
- Quy tắc dự án cho thay đổi hiển thị trong `pema-agent/frontend`: ghi mục vào `web-design-changes.md` cùng commit (tab "Tri
  thức" là thay đổi hiển thị), chạy `pending-web.cjs`, `pnpm inventory`; trang của plugin nằm ngoài `src/` của clinic web nên
  chỉ cần ghi mục "Kho tri thức" như một nhóm trang mới. Khi làm UI thật dùng subagent `pema-ui-builder` và so với ảnh canvas nếu
  có khung tương ứng; không có thì nói rõ trong báo cáo và ghi vào log.
- Kiểm thử: test thuần cho logic (lọc, nhóm, định dạng tiến độ, đọc YAML, bước cảnh báo) cạnh mã; test trang bằng `fetch` giả
  như các trang Model/Phiên chat; một test đầu-cuối trên mock cho luồng "tải tệp → xem trước → nạp → thấy dòng Sẵn sàng".
- Màn hình nào có thể bỏ trong bản demo: Lịch sử, Câu hỏi chưa có tài liệu, Dịch vụ nhập từ bảng, tách nguồn.

## 9. Các bước làm (gắn với bảng bước của plan RAG, mục 19.4)

| Bước | Backend (plan RAG) | UI của bước này | Dùng được gì |
|---|---|---|---|
| U0 | Lõi: migration plugin, SDK `section` | tab "Kho tri thức" hiện khi plugin bật; trang trống "Chưa có nguồn nào" | khung sẵn |
| U1 | Bước 1: nạp `.md/.txt/.docx/.xlsx`, chia đoạn, BM25 | **Nguồn** (bảng, lọc, tiến độ, Duyệt, Đối tượng, Xóa) + **Thêm nguồn** (tải tệp, gõ văn bản, **nhập hàng loạt .md/zip có YAML**) + Xem trước tối thiểu (số đoạn, cảnh báo cơ bản) | nạp được bộ demo 22 tệp trong vài phút bằng chuột |
| U2 | Bước 2–3: PDF, Docling, nhãn dịch vụ | Chi tiết nguồn (bản dựng cấu trúc, đoạn, tách nguồn), **Dịch vụ**, cảnh báo đầy đủ ở Xem trước | nạp cẩm nang PDF thật, sửa cấu trúc |
| U3 | Bước 4: vector, RRF | **Cài đặt** (embedding + Kiểm tra kết nối + Nhúng lại), **Thử tìm** theo tầng | thấy vector mua được gì |
| U4 | Bước 5: rerank, `kb_read`, bộ đo | Thử tìm có xếp lại và "Dùng làm ca đo", **Câu hỏi chưa có tài liệu**, Lịch sử | vòng phản hồi |
| U5 | Bước 6: chuyển `/guide`, bỏ RAG ở clinic API | công cụ chuyển một lần các nguồn `guide` | clinic API không còn RAG |

Cho buổi demo gọi vốn tối thiểu cần U0 + U1 + phần Kiểm tra kết nối của U3 (để cắm khóa embedding mà không phải sửa file).

## 10. Quyết định của user (2026-10-12)

> **Cập nhật 2026-10-12 (user): một kho chung cho mọi kênh, không chia Bệnh nhân / Nội bộ.** Mục tiêu lúc này là thử
> agent RAG và độ chính xác trả lời theo tài liệu (qua Zalo cá nhân quét QR), chưa lo phân quyền hay nguồn gốc. UI ẩn
> "Đối tượng" ở mọi chỗ (bảng, lọc, thao tác hàng loạt, chi tiết, Thêm nguồn, "Như kênh" ở Thử tìm, "Tiền tố kênh bệnh
> nhân" ở Cài đặt) bằng cờ `AUDIENCE_SPLIT = false` (`ui/src/logic.ts`). Backend: `kb_search` **không lọc theo kênh hay
> `audience`**; vẫn lọc theo tenant, `lifecycle = active` và hiệu lực theo ngày hỏi (đó là độ chính xác, không phải phân
> quyền). `doc_id` vẫn đi kèm mỗi đoạn để đo và trích dẫn. Muốn chia lại: đổi cờ thành `true` và bật lại lọc kênh.

> **Cập nhật 2026-10-12 (user): tạm ẩn và bỏ qua bước duyệt.** Có dữ liệu là agent lấy ra dùng ngay khi nguồn sẵn sàng.
> UI ẩn cột/lọc/nút "Duyệt" và cài đặt "Kênh bệnh nhân chỉ thấy nguồn đã duyệt" bằng cờ `APPROVAL_STEP = false`
> (`ui/src/logic.ts`); mô hình dữ liệu vẫn giữ `approved` và nguồn mới luôn `approved = true`. Backend (bước 1 trở đi)
> **không lọc theo `approved`**. Lọc theo đối tượng (Nội bộ / Bệnh nhân), hiệu lực và tenant vẫn giữ. Muốn bật lại: đổi cờ
> thành `true` và bật lại bộ lọc ở backend. Các chỗ nói "duyệt" ở mục 3, 6, 7 dưới đây là thiết kế khi bật lại.

1. Tên tab: **"Kho tri thức"** (không phải "Tri thức"/"Hiểu biết").
2. **Tab riêng cấp 1** trong "Điều khiển agent", qua `Contribution.section`. Lý do user: RAG là một plugin, Zalo là một plugin
   khác; plugin chỉ là giao diện cho người dùng, kho tri thức không nằm lẫn trong trang Plugins.
3. Nhập hàng loạt: tài liệu có `audience: patient` trong YAML vào thẳng **"Bệnh nhân + đã duyệt"** (khỏi bấm duyệt 18 lần);
   `audience: staff` vào "Nội bộ + đã duyệt"; tài liệu không có YAML vẫn mặc định **Nội bộ + chưa duyệt** (mục 7). Ở bước 2
   người dùng thấy rõ và đổi được trước khi nạp. (Khi dùng cho bệnh nhân thật phải xem lại mặc định này.)
4. **Dựng UI** (chưa có backend): làm đủ màn hình trên mock (`pnpm dev:mock`), backend theo các bước của plan RAG sau.
